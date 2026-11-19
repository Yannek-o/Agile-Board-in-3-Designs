from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.backlog.models import BacklogItem, Release
from apps.backlog.queries import release_progress
from apps.backlog.services import archive_item, change_item_status, publish_release
from apps.projects.models import ProjectMembership
from tests.factories import add_member, make_item, make_project, make_user

Access = ProjectMembership.AccessLevel
Status = BacklogItem.Status


class ReleaseServiceTests(TestCase):
    def setUp(self):
        self.project = make_project("REL")
        self.lead = make_user()
        add_member(self.project, self.lead, access_level=Access.MANAGE)
        self.release = Release.objects.create(
            project=self.project, name="v1.0", release_date=date(2026, 12, 1)
        )

    def test_progress_counts_active_items(self):
        done = make_item(self.project, fix_version=self.release, story_points=5)
        make_item(self.project, fix_version=self.release, story_points=3)
        archived = make_item(self.project, fix_version=self.release, story_points=8)
        change_item_status(done, Status.DONE, actor=self.lead)
        archive_item(archived, actor=self.lead)
        row = release_progress(self.project)[0]
        self.assertEqual(row["release"], self.release)
        self.assertEqual((row["items"], row["done_items"]), (2, 1))
        self.assertEqual((row["points"], row["done_points"]), (8, 5))
        self.assertEqual(row["percent"], 50)

    def test_fix_version_must_belong_to_same_project(self):
        foreign = Release.objects.create(project=make_project("OTH"), name="x")
        with self.assertRaises(ValidationError):
            make_item(self.project, fix_version=foreign)

    def test_publishing_marks_release_and_reports_open_items(self):
        make_item(self.project, fix_version=self.release)
        open_count = publish_release(self.release, actor=self.lead)
        self.release.refresh_from_db()
        self.assertEqual(open_count, 1)
        self.assertEqual(self.release.status, Release.Status.RELEASED)
        self.assertIsNotNone(self.release.released_at)

    def test_release_names_are_unique_per_project(self):
        with self.assertRaises(ValidationError):
            Release(project=self.project, name="V1.0").full_clean()


class ReleaseViewTests(TestCase):
    def setUp(self):
        self.project = make_project("REL")
        self.lead = make_user()
        self.editor = make_user()
        add_member(self.project, self.lead, access_level=Access.MANAGE)
        add_member(self.project, self.editor, access_level=Access.EDIT)
        self.url = reverse("backlog:releases", args=["REL"])

    def test_lead_creates_release(self):
        self.client.force_login(self.lead)
        response = self.client.post(
            self.url,
            {"name": "v2.0", "release_date": "2026-12-15", "description": "Winter"},
        )
        self.assertRedirects(response, self.url)
        self.assertContains(self.client.get(self.url), "v2.0")

    def test_editor_sees_releases_but_cannot_create(self):
        self.client.force_login(self.editor)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.post(self.url, {"name": "x"}).status_code, 403)

    def test_publish_view_and_filter(self):
        release = Release.objects.create(project=self.project, name="v3.0")
        make_item(self.project, title="Im Release", fix_version=release)
        make_item(self.project, title="Ohne Release")
        self.client.force_login(self.lead)
        listing = self.client.get(
            reverse("backlog:list", args=["REL"]), {"release": release.pk}
        )
        titles = [item.title for item in listing.context["items"]]
        self.assertEqual(titles, ["Im Release"])
        self.client.post(reverse("backlog:release_publish", args=["REL", release.pk]))
        release.refresh_from_db()
        self.assertEqual(release.status, Release.Status.RELEASED)

    def test_item_form_offers_only_unreleased_versions(self):
        open_release = Release.objects.create(project=self.project, name="offen")
        Release.objects.create(
            project=self.project, name="alt", status=Release.Status.RELEASED
        )
        self.client.force_login(self.lead)
        form = self.client.get(reverse("backlog:create", args=["REL"])).context["form"]
        self.assertEqual(list(form.fields["fix_version"].queryset), [open_release])
