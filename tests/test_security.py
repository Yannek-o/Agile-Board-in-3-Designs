from datetime import timedelta

from django.contrib import admin
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.forms import ThrottledAdminAuthenticationForm
from apps.accounts.models import AuthAttempt
from tests.factories import DEFAULT_PASSWORD, make_user

LOCKOUT_SETTINGS = {
    "LOGIN_FAILURE_LIMIT": 3,
    "LOGIN_IP_FAILURE_LIMIT": 5,
    "LOGIN_LOCKOUT_MINUTES": 15,
}


@override_settings(**LOCKOUT_SETTINGS)
class LoginLockoutTests(TestCase):
    def setUp(self):
        self.user = make_user("ben")
        self.url = reverse("accounts:login")

    def attempt(self, password, username="ben"):
        return self.client.post(
            self.url, {"username": username, "password": password}
        )

    def test_account_is_locked_after_repeated_failures(self):
        for _ in range(3):
            self.attempt("falsch")
        response = self.attempt(DEFAULT_PASSWORD)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Zu viele fehlgeschlagene Anmeldeversuche")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_lock_is_case_insensitive_for_username(self):
        for _ in range(3):
            self.attempt("falsch", username="BEN")
        self.attempt(DEFAULT_PASSWORD)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_lock_expires_after_lockout_period(self):
        for _ in range(3):
            self.attempt("falsch")
        AuthAttempt.objects.update(
            created_at=AuthAttempt.objects.first().created_at - timedelta(minutes=16)
        )
        self.attempt(DEFAULT_PASSWORD)
        self.assertIn("_auth_user_id", self.client.session)

    def test_successful_login_resets_failures(self):
        for _ in range(2):
            self.attempt("falsch")
        self.attempt(DEFAULT_PASSWORD)
        self.client.logout()
        for _ in range(2):
            self.attempt("falsch")
        self.attempt(DEFAULT_PASSWORD)
        self.assertIn("_auth_user_id", self.client.session)

    def test_ip_is_locked_after_failures_across_usernames(self):
        for index in range(5):
            self.attempt("falsch", username=f"unbekannt{index}")
        self.attempt(DEFAULT_PASSWORD)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_admin_login_uses_throttled_form(self):
        self.assertIs(admin.site.login_form, ThrottledAdminAuthenticationForm)


@override_settings(SITE_URL="https://agile.example.com", PASSWORD_RESET_IP_LIMIT=2)
class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = make_user("ben", email="ben@example.com")

    def request_reset(self, email):
        return self.client.post(reverse("accounts:password_reset"), {"email": email})

    def test_reset_page_is_public_and_linked_from_login(self):
        self.assertEqual(
            self.client.get(reverse("accounts:password_reset")).status_code, 200
        )
        self.assertContains(
            self.client.get(reverse("accounts:login")),
            reverse("accounts:password_reset"),
        )

    def test_full_reset_flow(self):
        response = self.request_reset("BEN@example.com")
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn("https://agile.example.com/accounts/reset/", body)
        link = next(
            line for line in body.splitlines() if "/accounts/reset/" in line
        ).strip()
        path = link.replace("https://agile.example.com", "")
        response = self.client.get(path, follow=True)
        new_password = "Neues-Passwort-2026!"
        response = self.client.post(
            response.redirect_chain[-1][0],
            {"new_password1": new_password, "new_password2": new_password},
        )
        self.assertRedirects(response, reverse("accounts:password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))

    def test_unknown_or_inactive_address_sends_nothing(self):
        make_user("ehemalig", email="alt@example.com", is_active=False)
        for email in ("niemand@example.com", "alt@example.com"):
            response = self.request_reset(email)
            self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_requests_are_limited_per_ip(self):
        for _ in range(3):
            response = self.request_reset("ben@example.com")
            self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 2)
