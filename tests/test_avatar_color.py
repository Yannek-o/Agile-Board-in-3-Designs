from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from tests.factories import add_member, make_project, make_user


class AvatarColorTests(TestCase):
    def setUp(self):
        self.user = make_user(first_name="Ben", last_name="Becker")
        self.url = reverse("accounts:avatar_color")
        self.dashboard_url = reverse("reporting:dashboard")
        self.client.force_login(self.user)

    def save(self, **data):
        return self.client.post(self.url, data, HTTP_ACCEPT="application/json")

    def test_default_avatar_uses_design_colours(self):
        self.assertEqual(self.user.avatar_background, "")
        response = self.client.get(self.dashboard_url)
        self.assertNotContains(response, "--avatar-bg")

    def test_single_colour_is_stored_and_rendered(self):
        response = self.save(color="#FF6B00")
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar_color, "#ff6b00")
        self.assertEqual(self.user.avatar_background, "#ff6b00")
        page = self.client.get(self.dashboard_url)
        self.assertContains(page, "--avatar-bg: #ff6b00")
        self.assertContains(page, "has-color")

    def test_gradient_uses_both_colours(self):
        self.save(color="#ff6b00", color_2="#8b5cf6", gradient="1")
        self.user.refresh_from_db()
        self.assertEqual(
            self.user.avatar_background,
            "linear-gradient(135deg, #ff6b00 0%, #8b5cf6 100%)",
        )

    def test_second_colour_is_dropped_without_gradient(self):
        self.save(color="#ff6b00", color_2="#8b5cf6")
        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar_color_2, "")

    def test_text_stays_readable(self):
        self.save(color="#ffe066")
        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar_text_color, "#1a1a1a")
        self.save(color="#1e3a8a")
        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar_text_color, "#ffffff")

    def test_invalid_colour_is_rejected(self):
        self.save(color="#ff6b00")
        response = self.save(color="red;background:url(x)")
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar_color, "#ff6b00")

    def test_reset_restores_design_colours(self):
        self.save(color="#ff6b00", color_2="#8b5cf6", gradient="1")
        self.save(reset="1")
        self.user.refresh_from_db()
        self.assertEqual((self.user.avatar_color, self.user.avatar_color_2), ("", ""))

    def test_colour_applies_in_every_design_and_for_colleagues(self):
        self.save(color="#22c55e")
        self.user.refresh_from_db()
        self.user.design = User.Design.PATINA
        self.user.save(update_fields=["design"])
        self.assertContains(
            self.client.get(self.dashboard_url), "--avatar-bg: #22c55e"
        )
        project = make_project("COL")
        colleague = make_user()
        add_member(project, self.user)
        add_member(project, colleague)
        self.client.force_login(colleague)
        response = self.client.get(reverse("projects:team", args=["COL"]))
        self.assertContains(response, "--avatar-bg: #22c55e")

    def test_switch_requires_post(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_form_post_redirects_back(self):
        response = self.client.post(
            self.url, {"color": "#ff6b00", "next": "/projects/"}
        )
        self.assertRedirects(response, "/projects/", fetch_redirect_response=False)
