import json

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.backlog.models import BacklogItem
from apps.backlog.services import archive_item
from apps.projects.models import ProjectMembership
from apps.sprints.models import SprintItem
from apps.sprints.services import move_item_to_sprint, start_sprint
from tests.factories import add_member, make_item, make_project, make_sprint, make_user

Access = ProjectMembership.AccessLevel
Type = BacklogItem.ItemType
Outcome = SprintItem.Outcome


def open_sprint_of(item):
    entry = item.sprint_entries.filter(outcome=Outcome.OPEN).first()
    return entry.sprint if entry else None


class MoveItemToSprintTests(TestCase):
    def setUp(self):
        self.project = make_project("PLAN")
        self.user = make_user()
        add_member(self.project, self.user, access_level=Access.MANAGE)
        self.sprint_one = make_sprint(self.project)
        self.sprint_two = make_sprint(self.project)
        self.item = make_item(self.project, story_points=3)

    def test_backlog_item_moves_into_sprint(self):
        move_item_to_sprint(self.item, self.sprint_one, actor=self.user)
        self.assertEqual(open_sprint_of(self.item), self.sprint_one)

    def test_item_moves_between_sprints(self):
        move_item_to_sprint(self.item, self.sprint_one, actor=self.user)
        move_item_to_sprint(self.item, self.sprint_two, actor=self.user)
        self.assertEqual(open_sprint_of(self.item), self.sprint_two)
        old_entry = SprintItem.objects.get(sprint=self.sprint_one, item=self.item)
        self.assertEqual(old_entry.outcome, Outcome.REMOVED)

    def test_archiving_removes_item_from_open_sprint(self):
        move_item_to_sprint(self.item, self.sprint_one, actor=self.user)
        start_sprint(self.sprint_one, actor=self.user)
        archive_item(self.item, actor=self.user)
        entry = SprintItem.objects.get(sprint=self.sprint_one, item=self.item)
        self.assertEqual(entry.outcome, Outcome.REMOVED)
        self.assertNotIn(self.item, self.sprint_one.open_items())
        self.client.force_login(self.user)
        board = self.client.get(reverse("board:board", args=["PLAN"]))
        self.assertNotContains(board, f'data-item="{self.item.number}"')

    def test_archived_items_never_count_as_open_sprint_items(self):
        move_item_to_sprint(self.item, self.sprint_one, actor=self.user)
        BacklogItem.objects.filter(pk=self.item.pk).update(archived_at=timezone.now())
        self.assertNotIn(self.item, self.sprint_one.open_items())
        self.assertEqual(self.sprint_one.committed_points(), 0)

    def test_item_moves_back_to_backlog(self):
        move_item_to_sprint(self.item, self.sprint_one, actor=self.user)
        move_item_to_sprint(self.item, None, actor=self.user)
        self.assertIsNone(open_sprint_of(self.item))

    def test_moving_to_current_sprint_changes_nothing(self):
        move_item_to_sprint(self.item, self.sprint_one, actor=self.user)
        move_item_to_sprint(self.item, self.sprint_one, actor=self.user)
        self.assertEqual(SprintItem.objects.filter(item=self.item).count(), 1)


class BacklogPlanningViewTests(TestCase):
    def setUp(self):
        self.project = make_project("PLAN")
        self.manager = make_user()
        self.reader = make_user()
        add_member(self.project, self.manager, access_level=Access.MANAGE)
        add_member(self.project, self.reader, access_level=Access.READ)
        self.active = make_sprint(self.project, name="Aktiver Sprint")
        self.planned = make_sprint(self.project, name="Naechster Sprint")
        self.epic = make_item(self.project, item_type=Type.EPIC, title="Epic Login")
        self.in_sprint = make_item(
            self.project, title="Im Sprint", story_points=5, parent=self.epic
        )
        self.unplanned = make_item(
            self.project, title="Offen im Backlog", story_points=2
        )
        self.subtask = make_item(
            self.project, item_type=Type.SUBTASK, title="Teilaufgabe",
            parent=self.in_sprint,
        )
        move_item_to_sprint(self.in_sprint, self.active, actor=self.manager)
        start_sprint(self.active, actor=self.manager)
        self.url = reverse("backlog:planning", args=["PLAN"])
        self.move_url = reverse("backlog:plan_move", args=["PLAN"])

    def test_page_groups_items_by_sprint_and_backlog(self):
        self.client.force_login(self.reader)
        response = self.client.get(self.url)
        sections = response.context["sections"]
        self.assertEqual(
            [section["title"] for section in sections],
            ["Aktiver Sprint", "Naechster Sprint", "Backlog"],
        )
        self.assertEqual(list(sections[0]["items"]), [self.in_sprint])
        self.assertEqual(sections[0]["points"], 5)
        self.assertEqual(list(sections[2]["items"]), [self.unplanned])
        self.assertNotContains(response, "Teilaufgabe")
        self.assertContains(response, "Epic Login")

    def post_json(self, payload):
        return self.client.post(
            self.move_url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )

    def test_manager_moves_item_with_json(self):
        self.client.force_login(self.manager)
        response = self.post_json(
            {"item": self.unplanned.number, "sprint": self.planned.number}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(open_sprint_of(self.unplanned), self.planned)
        response = self.post_json({"item": self.unplanned.number, "sprint": None})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(open_sprint_of(self.unplanned))

    def test_form_fallback_moves_item(self):
        self.client.force_login(self.manager)
        payload = {"item": self.unplanned.number, "sprint": self.planned.number}
        response = self.client.post(self.move_url, payload)
        self.assertRedirects(response, self.url)
        self.assertEqual(open_sprint_of(self.unplanned), self.planned)

    def test_epic_cannot_be_moved_into_sprint(self):
        self.client.force_login(self.manager)
        response = self.post_json(
            {"item": self.epic.number, "sprint": self.planned.number}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Epics", response.json()["error"])

    def test_reader_cannot_move(self):
        self.client.force_login(self.reader)
        payload = {"item": self.unplanned.number, "sprint": self.planned.number}
        response = self.client.post(self.move_url, payload)
        self.assertEqual(response.status_code, 403)

    def test_backlog_shortcut_opens_planning(self):
        self.client.force_login(self.reader)
        self.client.get(reverse("projects:detail", args=["PLAN"]))
        response = self.client.get(reverse("core:go", args=["backlog"]))
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
