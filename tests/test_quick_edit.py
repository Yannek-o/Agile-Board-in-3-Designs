import json
from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.activity.models import ActivityEvent
from apps.backlog.models import BacklogItem
from apps.projects.models import ProjectMembership
from apps.sprints.models import SprintItem
from apps.sprints.services import add_item_to_sprint, start_sprint
from tests.factories import add_member, make_item, make_project, make_sprint, make_user

Access = ProjectMembership.AccessLevel
Status = BacklogItem.Status


class JsonClientMixin:
    def post_json(self, url, payload):
        return self.client.post(
            url, data=json.dumps(payload), content_type="application/json",
            HTTP_ACCEPT="application/json",
        )


class QuickCreateTests(JsonClientMixin, TestCase):
    def setUp(self):
        self.project = make_project("QUIK")
        self.manager = make_user()
        self.editor = make_user()
        add_member(self.project, self.manager, access_level=Access.MANAGE)
        add_member(self.project, self.editor, access_level=Access.EDIT)
        self.sprint = make_sprint(self.project)
        add_item_to_sprint(self.sprint, make_item(self.project), actor=self.manager)
        start_sprint(self.sprint, actor=self.manager)
        self.url = reverse("board:quick_create", args=["QUIK"])

    def test_manager_creates_item_in_column_of_active_sprint(self):
        self.client.force_login(self.manager)
        response = self.post_json(
            self.url,
            {"title": "Neue Karte", "status": Status.IN_PROGRESS, "item_type": "bug"},
        )
        self.assertEqual(response.status_code, 201)
        item = BacklogItem.objects.get(title="Neue Karte")
        self.assertEqual(item.status, Status.IN_PROGRESS)
        self.assertEqual(item.item_type, "bug")
        self.assertTrue(
            SprintItem.objects.filter(
                sprint=self.sprint, item=item, outcome=SprintItem.Outcome.OPEN
            ).exists()
        )
        self.assertIn("revision", response.json())

    def test_form_fallback_redirects_to_board(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            self.url, {"title": "Per Formular", "status": Status.TODO}
        )
        self.assertRedirects(response, reverse("board:board", args=["QUIK"]))
        self.assertTrue(BacklogItem.objects.filter(title="Per Formular").exists())

    def test_empty_title_and_done_column_are_rejected(self):
        self.client.force_login(self.manager)
        empty = self.post_json(self.url, {"title": "  ", "status": Status.TODO})
        self.assertEqual(empty.status_code, 400)
        done = self.post_json(self.url, {"title": "Fertig", "status": Status.DONE})
        self.assertEqual(done.status_code, 400)
        self.assertFalse(BacklogItem.objects.filter(title="Fertig").exists())

    def test_requires_backlog_planning_rights(self):
        self.client.force_login(self.editor)
        response = self.post_json(self.url, {"title": "X", "status": Status.TODO})
        self.assertEqual(response.status_code, 403)

    def test_board_offers_quick_create_only_to_planners(self):
        self.client.force_login(self.manager)
        page = self.client.get(reverse("board:board", args=["QUIK"]))
        self.assertContains(page, "data-quick-create", count=3)
        self.client.force_login(self.editor)
        page = self.client.get(reverse("board:board", args=["QUIK"]))
        self.assertNotContains(page, "data-quick-create")


class InlineUpdateTests(JsonClientMixin, TestCase):
    def setUp(self):
        self.project = make_project("QUIK")
        self.manager = make_user()
        self.editor = make_user()
        self.reader = make_user()
        add_member(self.project, self.manager, access_level=Access.MANAGE)
        add_member(self.project, self.editor, access_level=Access.EDIT)
        add_member(self.project, self.reader, access_level=Access.READ)
        self.item = make_item(self.project, title="Alt", story_points=3)
        self.url = reverse("backlog:inline_update", args=["QUIK", self.item.number])

    def update(self, field, value, version=None):
        return self.post_json(
            self.url,
            {"field": field, "value": value, "version": version or self.item.version},
        )

    def test_manager_changes_title(self):
        self.client.force_login(self.manager)
        response = self.update("title", "Neu")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["display"], "Neu")
        self.assertEqual(body["version"], self.item.version + 1)
        self.item.refresh_from_db()
        self.assertEqual(self.item.title, "Neu")
        self.assertTrue(
            ActivityEvent.objects.filter(item=self.item, field="title").exists()
        )

    def test_typed_fields_are_converted(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.update("story_points", "8").json()["display"], "8")
        self.item.refresh_from_db()
        self.assertEqual(self.update("story_points", "").json()["display"], "–")
        self.item.refresh_from_db()
        self.update("due_date", "2026-12-24")
        self.item.refresh_from_db()
        self.assertEqual(self.item.due_date, date(2026, 12, 24))
        self.update("assignee", str(self.editor.pk))
        self.item.refresh_from_db()
        self.assertEqual(self.item.assignee, self.editor)

    def test_invalid_values_are_rejected(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.update("priority", "urgent").status_code, 400)
        self.assertEqual(self.update("story_points", "500").status_code, 400)
        self.assertEqual(self.update("title", " ").status_code, 400)
        self.assertEqual(self.update("version", "9").status_code, 400)
        unknown_user = str(self.reader.pk + 999)
        self.assertEqual(self.update("assignee", unknown_user).status_code, 400)

    def test_stale_version_returns_conflict(self):
        self.client.force_login(self.manager)
        self.update("title", "Erste Änderung")
        response = self.update("title", "Zweite Änderung", version=self.item.version)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["display"], "Erste Änderung")

    def test_editor_cannot_change_planning_fields(self):
        self.client.force_login(self.editor)
        self.assertEqual(self.update("title", "Nein").status_code, 403)
        self.assertEqual(self.update("assignee", str(self.editor.pk)).status_code, 200)

    def test_reader_cannot_edit_and_sees_no_inline_fields(self):
        detail_url = reverse("backlog:detail", args=["QUIK", self.item.number])
        self.client.force_login(self.reader)
        self.assertEqual(self.update("description", "x").status_code, 403)
        page = self.client.get(detail_url)
        self.assertNotContains(page, "data-inline-field")
        self.client.force_login(self.manager)
        page = self.client.get(detail_url)
        self.assertContains(page, 'data-inline-field="title"')
