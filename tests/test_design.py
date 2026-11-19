from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from tests.factories import make_user

Design = User.Design


class DesignChoiceTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.dashboard_url = reverse("reporting:dashboard")
        self.switch_url = reverse("accounts:design")

    def test_new_users_get_neon(self):
        self.assertEqual(self.user.design, Design.NEON)
        self.client.force_login(self.user)
        response = self.client.get(self.dashboard_url)
        self.assertContains(response, 'data-design="neon"')
        self.assertContains(response, "js/theme.js")
        self.assertContains(response, "data-theme-toggle")
        self.assertNotContains(response, "css/patina.css")
        self.assertNotContains(response, "data-theme-slider")

    def test_patina_users_get_patina_assets_and_slider(self):
        self.user.design = Design.PATINA
        self.user.save()
        self.client.force_login(self.user)
        response = self.client.get(self.dashboard_url)
        self.assertContains(response, 'data-design="patina"')
        self.assertRegex(response.content.decode(), r"css/patina\.css\?v=[0-9a-f]{8}")
        self.assertContains(response, "js/patina-theme.js")
        self.assertContains(response, "data-theme-slider")
        self.assertNotContains(response, "data-theme-toggle")
        self.assertNotContains(response, "js/theme.js")

    def test_kalt_users_get_kalt_assets_and_theme_toggle(self):
        self.user.design = Design.KALT
        self.user.save()
        self.client.force_login(self.user)
        response = self.client.get(self.dashboard_url)
        self.assertContains(response, 'data-design="kalt"')
        self.assertRegex(response.content.decode(), r"css/kalt\.css\?v=[0-9a-f]{8}")
        self.assertContains(response, "js/theme.js")
        self.assertContains(response, "data-theme-toggle")
        self.assertNotContains(response, "css/patina.css")
        self.assertNotContains(response, "data-theme-slider")

    def test_switching_to_kalt_is_stored(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.switch_url, {"design": Design.KALT}, HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.design, Design.KALT)

    def test_switching_design_is_stored_per_user(self):
        other = make_user()
        self.client.force_login(self.user)
        response = self.client.post(
            self.switch_url, {"design": Design.PATINA, "next": "/projects/"}
        )
        self.assertRedirects(response, "/projects/", fetch_redirect_response=False)
        self.user.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.user.design, Design.PATINA)
        self.assertEqual(other.design, Design.NEON)

    def test_unknown_design_is_rejected(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.switch_url, {"design": "comic"}, HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.design, Design.NEON)

    def test_foreign_redirect_target_is_ignored(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.switch_url,
            {"design": Design.PATINA, "next": "https://evil.example/"},
        )
        self.assertRedirects(
            response, self.dashboard_url, fetch_redirect_response=False
        )

    def test_switch_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.switch_url).status_code, 405)

    def test_user_menu_offers_all_designs(self):
        self.client.force_login(self.user)
        response = self.client.get(self.dashboard_url)
        self.assertContains(response, 'name="design" value="neon"')
        self.assertContains(response, 'name="design" value="patina"')
        self.assertContains(response, 'name="design" value="kalt"')
        self.assertContains(
            response, 'class="design-option design-neon" aria-pressed="true"'
        )

    def test_profile_form_saves_design(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("accounts:profile"),
            {
                "first_name": "Anna",
                "last_name": "A",
                "email": "anna@example.com",
                "job_title": "",
                "email_notifications": "on",
                "design": Design.PATINA,
            },
        )
        self.assertRedirects(response, reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.design, Design.PATINA)

    def test_login_page_uses_neon(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertNotContains(response, "css/patina.css")
