from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.backlog.models import BacklogItem
from apps.backlog.queries import epic_progress
from apps.backlog.services import archive_item, change_item_status
from apps.projects.models import ProjectMembership
from tests.factories import add_member, make_item, make_project, make_user

Access = ProjectMembership.AccessLevel
Type = BacklogItem.ItemType


class EpicProgressTests(TestCase):
    def setUp(self):
        self.project = make_project("EPC")
        self.user = make_user()
        add_member(self.project, self.user, access_level=Access.MANAGE)
        self.epic = make_item(
            self.project, item_type=Type.EPIC, title="Zahlungen", color="#c8873e"
        )

    def test_progress_sums_points_of_active_children(self):
        done = make_item(self.project, parent=self.epic, story_points=5)
        make_item(self.project, parent=self.epic, story_points=3)
        archived = make_item(self.project, parent=self.epic, story_points=8)
        change_item_status(done, BacklogItem.Status.DONE, actor=self.user)
        archive_item(archived, actor=self.user)

        progress = epic_progress(self.project)[0]
        self.assertEqual(progress["epic"], self.epic)
        self.assertEqual(progress["items"], 2)
        self.assertEqual(progress["done_items"], 1)
        self.assertEqual(progress["done_points"], 5)
        self.assertEqual(progress["total_points"], 8)
        self.assertEqual(progress["percent"], 62)

    def test_archived_epics_are_not_listed(self):
        archive_item(self.epic, actor=self.user)
        self.assertEqual(epic_progress(self.project), [])

    def test_color_must_be_hex(self):
        with self.assertRaises(ValidationError):
            make_item(self.project, item_type=Type.EPIC, color="rot")


class EpicPageTests(TestCase):
    def setUp(self):
        self.project = make_project("EPC")
        self.planner = make_user()
        self.editor = make_user()
        add_member(self.project, self.planner, access_level=Access.MANAGE)
        add_member(self.project, self.editor, access_level=Access.EDIT)
        self.url = reverse("backlog:epics", args=["EPC"])

    def test_planner_creates_epic_with_color(self):
        self.client.force_login(self.planner)
        response = self.client.post(
            self.url, {"title": "Benachrichtigungen", "color": "#c8873e"}
        )
        self.assertRedirects(response, self.url)
        epic = BacklogItem.objects.get(project=self.project, item_type=Type.EPIC)
        self.assertEqual(epic.color, "#c8873e")
        page = self.client.get(self.url)
        self.assertContains(page, "Benachrichtigungen")
        self.assertContains(page, "--epic: #c8873e")

    def test_editor_sees_page_but_cannot_create(self):
        self.client.force_login(self.editor)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        response = self.client.post(self.url, {"title": "X", "color": "#000000"})
        self.assertEqual(response.status_code, 403)

    def test_backlog_filters_by_epic_including_subtasks(self):
        epic = make_item(self.project, item_type=Type.EPIC, title="Epic A")
        story = make_item(self.project, parent=epic, title="Story in A")
        make_item(
            self.project, item_type=Type.SUBTASK, parent=story, title="Teil von A"
        )
        make_item(self.project, title="Fremde Story")
        self.client.force_login(self.planner)
        response = self.client.get(
            reverse("backlog:list", args=["EPC"]), {"epic": epic.pk}
        )
        titles = [item.title for item in response.context["items"]]
        self.assertCountEqual(titles, ["Story in A", "Teil von A"])

    def test_color_field_only_offered_when_editing_epics(self):
        epic = make_item(self.project, item_type=Type.EPIC)
        story = make_item(self.project)
        self.client.force_login(self.planner)
        epic_form = self.client.get(
            reverse("backlog:edit", args=["EPC", epic.number])
        ).context["form"]
        story_form = self.client.get(
            reverse("backlog:edit", args=["EPC", story.number])
        ).context["form"]
        self.assertIn("color", epic_form.fields)
        self.assertNotIn("color", story_form.fields)
