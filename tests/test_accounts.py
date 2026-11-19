import re
from urllib.parse import urlparse

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import AccountEvent, User
from apps.accounts.services import AccountError, set_employee_active, update_employee
from tests.factories import DEFAULT_PASSWORD, make_admin, make_user


class AuthenticationTests(TestCase):
    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("reporting:dashboard"))
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next=/",
            fetch_redirect_response=False,
        )

    def test_login_page_is_public(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anmelden")

    def test_valid_credentials_log_in(self):
        make_user("ben")
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "ben", "password": DEFAULT_PASSWORD},
        )
        self.assertRedirects(response, reverse("reporting:dashboard"))

    def test_invalid_credentials_are_rejected(self):
        make_user("ben")
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "ben", "password": "falsch"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_user_cannot_log_in(self):
        make_user("ehemalig", is_active=False)
        self.client.post(
            reverse("accounts:login"),
            {"username": "ehemalig", "password": DEFAULT_PASSWORD},
        )
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_requires_post(self):
        self.client.force_login(make_user())
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(
            response, reverse("accounts:login"), fetch_redirect_response=False
        )

    def test_no_public_registration_route_exists(self):
        response = self.client.get("/accounts/register/")
        self.assertIn(response.status_code, (302, 404))


class ProfileTests(TestCase):
    def test_user_can_update_own_profile(self):
        user = make_user("ben")
        self.client.force_login(user)
        response = self.client.post(
            reverse("accounts:profile"),
            {
                "first_name": "Ben",
                "last_name": "Becker",
                "email": "ben@example.com",
                "job_title": "Entwicklung",
            },
        )
        self.assertRedirects(response, reverse("accounts:profile"))
        user.refresh_from_db()
        self.assertEqual(user.job_title, "Entwicklung")
        self.assertEqual(user.initials, "BB")

    def test_profile_form_cannot_escalate_privileges(self):
        user = make_user("ben")
        self.client.force_login(user)
        self.client.post(
            reverse("accounts:profile"),
            {
                "first_name": "V",
                "last_name": "A",
                "email": "v@example.com",
                "is_staff": "on",
                "is_superuser": "on",
            },
        )
        user.refresh_from_db()
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)


class UserManagementTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.employee = make_user("mitarbeiter")

    def test_regular_employee_cannot_manage_users(self):
        self.client.force_login(self.employee)
        self.assertEqual(
            self.client.get(reverse("accounts:user_list")).status_code, 403
        )
        self.assertEqual(
            self.client.post(
                reverse("accounts:user_toggle_active", args=[self.admin.pk])
            ).status_code,
            403,
        )

    def test_admin_invites_employee_who_sets_own_password(self):
        self.client.force_login(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("accounts:user_create"),
                {
                    "username": "anna",
                    "first_name": "Anna",
                    "last_name": "S",
                    "email": "anna@example.com",
                    "job_title": "Product Owner",
                },
            )
        self.assertRedirects(response, reverse("accounts:user_list"))
        created = User.objects.get(username="anna")
        self.assertFalse(created.has_usable_password())
        self.assertFalse(created.is_staff)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["anna@example.com"])
        link = re.search(r"https?://\S+/accounts/invite/\S+/", mail.outbox[0].body)
        self.assertIsNotNone(link)

        self.client.logout()
        path = urlparse(link.group(0)).path
        form_page = self.client.get(path, follow=True)
        self.assertContains(form_page, "Passwort festlegen")
        new_password = "Neu-Passwort-2026!"
        self.client.post(
            form_page.redirect_chain[-1][0],
            {"new_password1": new_password, "new_password2": new_password},
        )
        created.refresh_from_db()
        self.assertTrue(created.check_password(new_password))
        reused = self.client.get(path, follow=True)
        self.assertNotContains(reused, 'name="new_password1"')

    def test_email_is_required_for_new_accounts(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("accounts:user_create"), {"username": "ohnemail"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="ohnemail").exists())

    def test_last_active_admin_can_neither_lose_rights_nor_be_deactivated(self):
        User.objects.filter(pk=self.admin.pk).update(is_superuser=False)
        self.admin.refresh_from_db()
        with self.assertRaises(AccountError):
            set_employee_active(self.admin, actor=self.employee, active=False)
        with self.assertRaises(AccountError):
            update_employee(self.admin, actor=self.employee, is_staff=False)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active and self.admin.is_staff)

        second_admin = make_admin("admin2")
        set_employee_active(self.admin, actor=second_admin, active=False)
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_active)

    def test_account_changes_are_logged_and_shown(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("accounts:user_edit", args=[self.employee.pk]),
            {
                "username": self.employee.username,
                "email": self.employee.email,
                "job_title": "Scrum Master",
            },
        )
        self.client.post(
            reverse("accounts:user_toggle_active", args=[self.employee.pk])
        )
        actions = list(
            AccountEvent.objects.filter(user=self.employee)
            .order_by("pk")
            .values_list("action", "actor")
        )
        self.assertEqual(
            actions,
            [
                (AccountEvent.Action.UPDATED, self.admin.pk),
                (AccountEvent.Action.DEACTIVATED, self.admin.pk),
            ],
        )
        page = self.client.get(reverse("accounts:user_edit", args=[self.employee.pk]))
        self.assertContains(page, "Funktion")
        self.assertContains(page, "Deaktiviert")

    def test_duplicate_email_is_rejected(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("accounts:user_create"),
            {"username": "neu", "email": self.employee.email.upper()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="neu").exists())

    def test_admin_deactivates_and_reactivates_employee(self):
        self.client.force_login(self.admin)
        url = reverse("accounts:user_toggle_active", args=[self.employee.pk])
        self.client.post(url)
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.is_active)
        self.client.post(url)
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)

    def test_admin_cannot_deactivate_own_account(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("accounts:user_toggle_active", args=[self.admin.pk])
        )
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_admin_edits_employee_permissions(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("accounts:user_edit", args=[self.employee.pk]),
            {
                "username": "mitarbeiter",
                "first_name": "Max",
                "last_name": "M",
                "email": "max@example.com",
                "job_title": "",
                "can_create_projects": "on",
            },
        )
        self.assertRedirects(response, reverse("accounts:user_list"))
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.can_create_projects)
