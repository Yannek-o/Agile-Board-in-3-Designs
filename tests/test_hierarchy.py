from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.activity.models import ActivityEvent
from apps.backlog.models import BacklogItem
from apps.backlog.services import change_item_status, update_backlog_item
from apps.projects.models import ProjectMembership
from apps.sprints.services import SprintError, add_item_to_sprint, start_sprint
from tests.factories import add_member, make_item, make_project, make_sprint, make_user

Access = ProjectMembership.AccessLevel
Type = BacklogItem.ItemType
Status = BacklogItem.Status


class HierarchyRuleTests(TestCase):
    def setUp(self):
        self.project = make_project("HIER")
        self.user = make_user()
        add_member(self.project, self.user, access_level=Access.MANAGE)
        self.epic = make_item(self.project, item_type=Type.EPIC, title="Epic")
        self.story = make_item(self.project, item_type=Type.STORY, parent=self.epic)

    def test_story_can_belong_to_epic(self):
        self.assertEqual(self.story.parent, self.epic)
        self.assertEqual(list(self.epic.children.all()), [self.story])

    def test_epic_cannot_have_parent(self):
        with self.assertRaises(ValidationError):
            make_item(self.project, item_type=Type.EPIC, parent=self.epic)

    def test_story_parent_must_be_epic(self):
        with self.assertRaises(ValidationError):
            make_item(self.project, item_type=Type.TASK, parent=self.story)

    def test_subtask_requires_non_epic_parent(self):
        with self.assertRaises(ValidationError):
            make_item(self.project, item_type=Type.SUBTASK)
        with self.assertRaises(ValidationError):
            make_item(self.project, item_type=Type.SUBTASK, parent=self.epic)
        subtask = make_item(self.project, item_type=Type.SUBTASK, parent=self.story)
        self.assertEqual(subtask.parent, self.story)

    def test_parent_must_belong_to_same_project(self):
        other = make_project("OTHR")
        foreign_epic = make_item(other, item_type=Type.EPIC)
        with self.assertRaises(ValidationError):
            make_item(self.project, item_type=Type.STORY, parent=foreign_epic)

    def test_item_cannot_be_its_own_parent(self):
        with self.assertRaises(ValidationError):
            update_backlog_item(
                self.story, actor=self.user, expected_version=None, parent=self.story
            )

    def test_child_progress_counts_done_children(self):
        second = make_item(self.project, item_type=Type.BUG, parent=self.epic)
        sprint = make_sprint(self.project)
        add_item_to_sprint(sprint, second, actor=self.user)
        start_sprint(sprint, actor=self.user)
        change_item_status(second, Status.DONE, actor=self.user)
        progress = self.epic.child_progress
        self.assertEqual((progress["done"], progress["total"]), (1, 2))
        self.assertEqual(progress["percent"], 50)

    def test_parent_change_is_recorded(self):
        story = make_item(self.project, item_type=Type.STORY)
        update_backlog_item(
            story, actor=self.user, expected_version=None, parent=self.epic
        )
        event = ActivityEvent.objects.filter(item=story, field="parent").get()
        self.assertEqual(event.new_value, self.epic.key)

    def test_epic_cannot_be_planned_into_sprint(self):
        sprint = make_sprint(self.project)
        with self.assertRaises(SprintError):
            add_item_to_sprint(sprint, self.epic, actor=self.user)


class HierarchyViewTests(TestCase):
    def setUp(self):
        self.project = make_project("HIER")
        self.user = make_user()
        add_member(self.project, self.user, access_level=Access.MANAGE)
        self.epic = make_item(self.project, item_type=Type.EPIC, title="Login-Epic")
        self.story = make_item(
            self.project, item_type=Type.STORY, title="Anmeldung", parent=self.epic
        )
        self.client.force_login(self.user)

    def test_detail_page_shows_parent_and_children(self):
        epic_page = self.client.get(
            reverse("backlog:detail", args=["HIER", self.epic.number])
        )
        self.assertContains(epic_page, "Untergeordnete Einträge")
        self.assertContains(epic_page, self.story.key)
        story_page = self.client.get(
            reverse("backlog:detail", args=["HIER", self.story.number])
        )
        self.assertContains(story_page, "Übergeordnet")
        self.assertContains(story_page, self.epic.key)

    def test_create_form_preselects_parent(self):
        response = self.client.get(
            reverse("backlog:create", args=["HIER"]) + f"?parent={self.story.number}"
        )
        form = response.context["form"]
        self.assertEqual(form.initial["parent"], self.story.pk)
        self.assertEqual(form.initial["item_type"], Type.SUBTASK)

    def test_create_subtask_via_form(self):
        response = self.client.post(
            reverse("backlog:create", args=["HIER"]),
            {
                "item_type": Type.SUBTASK,
                "title": "Passwortfeld",
                "priority": "medium",
                "status": Status.TODO,
                "parent": self.story.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        subtask = BacklogItem.objects.get(title="Passwortfeld")
        self.assertEqual(subtask.parent, self.story)

    def test_board_card_shows_epic_and_subtask_progress(self):
        make_item(self.project, item_type=Type.SUBTASK, parent=self.story)
        sprint = make_sprint(self.project)
        add_item_to_sprint(sprint, self.story, actor=self.user)
        start_sprint(sprint, actor=self.user)
        response = self.client.get(reverse("board:board", args=["HIER"]))
        self.assertContains(response, 'class="epic-chip"')
        self.assertContains(response, "Login-Epic")
        self.assertContains(response, "0/1 Unteraufgaben")
