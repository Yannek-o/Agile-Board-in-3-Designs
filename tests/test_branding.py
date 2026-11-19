import shutil
import tempfile
from pathlib import Path

from django.test import TestCase, override_settings
from django.urls import reverse

from tests.factories import make_admin, make_user


class BrandLogoTests(TestCase):
    def setUp(self):
        self.logo_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.logo_dir, ignore_errors=True)

    def test_text_brand_is_shown_without_logo_file(self):
        with override_settings(BRAND_LOGO_DIR=self.logo_dir):
            response = self.client.get(reverse("accounts:login"))
        self.assertContains(
            response,
            '<span class="brand-mark">Agile</span> <span class="brand-product">Board'
            "</span>",
            html=False,
        )
        self.assertNotContains(response, 'class="brand-logo"')

    def test_logo_image_is_used_when_file_exists(self):
        (self.logo_dir / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        with override_settings(BRAND_LOGO_DIR=self.logo_dir):
            response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, 'class="brand-logo"')
        self.assertContains(response, "img/brand/logo.png")
        self.assertContains(response, 'alt="Agile Board"')

    def test_svg_logo_is_preferred_over_png(self):
        (self.logo_dir / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (self.logo_dir / "logo.svg").write_text("<svg/>", encoding="utf-8")
        with override_settings(BRAND_LOGO_DIR=self.logo_dir):
            response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, "img/brand/logo.svg")


class ThemeTests(TestCase):
    def test_assets_carry_version_for_cache_busting(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertRegex(response.content.decode(), r"css/app\.css\?v=[0-9a-f]{8}")
        self.assertRegex(response.content.decode(), r"js/theme\.js\?v=[0-9a-f]{8}")

    def test_login_page_offers_theme_toggle_and_effects(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, "data-theme-toggle")
        self.assertContains(response, "js/theme.js")
        self.assertContains(response, "js/effects.js")

    def test_app_pages_offer_theme_toggle_and_effects(self):
        self.client.force_login(make_user())
        response = self.client.get(reverse("reporting:dashboard"))
        self.assertContains(response, "data-theme-toggle")
        self.assertContains(response, "js/theme.js")
        self.assertContains(response, "js/effects.js")
        self.assertContains(response, 'class="ab-backdrop"')


class NavigationBarTests(TestCase):
    def test_top_bar_marks_current_page(self):
        self.client.force_login(make_user())
        response = self.client.get(reverse("projects:list"))
        self.assertContains(response, 'class="ab-navbar"')
        self.assertContains(
            response,
            f'href="{reverse("projects:list")}" class="active" aria-current="page"',
        )
        self.assertContains(response, 'aria-controls="ab-primary-nav"')

    def test_admin_link_only_for_system_admins(self):
        self.client.force_login(make_user())
        response = self.client.get(reverse("reporting:dashboard"))
        self.assertNotContains(response, reverse("accounts:user_list"))
        self.client.force_login(make_admin())
        response = self.client.get(reverse("reporting:dashboard"))
        self.assertContains(response, reverse("accounts:user_list"))
