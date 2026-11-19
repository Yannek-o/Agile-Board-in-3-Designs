import json

from django.test import TestCase
from django.urls import reverse

from apps.backlog.models import BacklogItem
from apps.backlog.services import change_item_status
from apps.projects.models import ProjectMembership
from apps.sprints.services import add_item_to_sprint, start_sprint
from tests.factories import (
    add_member,
    make_item,
    make_project,
    make_sprint,
    make_user,
)

Access = ProjectMembership.AccessLevel
Status = BacklogItem.Status


class BoardTests(TestCase):
    def setUp(self):
        self.project = make_project("HELP")
        self.lead = make_user("lead", first_name="Anna", last_name="S")
        self.editor = make_user("editor", first_name="Ben", last_name="A")
        self.reader = make_user("reader")
        add_member(self.project, self.lead, access_level=Access.MANAGE)
        add_member(self.project, self.editor, access_level=Access.EDIT)
        add_member(self.project, self.reader, access_level=Access.READ)
        self.sprint = make_sprint(self.project, goal="Tickets verfolgen")
        self.item = make_item(
            self.project, title="Ticketkategorien verwalten",
            assignee=self.editor, priority=BacklogItem.Priority.HIGH,
        )
        self.other_item = make_item(
            self.project, title="E-Mail-Vorlagen", assignee=self.lead,
            priority=BacklogItem.Priority.LOW,
        )
        self.backlog_only = make_item(self.project, title="Nicht im Sprint")
        add_item_to_sprint(self.sprint, self.item, actor=self.lead)
        add_item_to_sprint(self.sprint, self.other_item, actor=self.lead)
        start_sprint(self.sprint, actor=self.lead)
        self.board_url = reverse("board:board", args=["HELP"])
        self.move_url = reverse("board:move", args=["HELP"])

    def move(self, item, status, version=None, as_json=True):
        payload = {
            "item": item.number,
            "status": status,
            "version": item.version if version is None else version,
        }
        if as_json:
            return self.client.post(
                self.move_url,
                data=json.dumps(payload),
                content_type="application/json",
                HTTP_ACCEPT="application/json",
            )
        return self.client.post(self.move_url, payload)

    def test_board_shows_only_active_sprint_items_in_columns(self):
        self.client.force_login(self.reader)
        response = self.client.get(self.board_url)
        self.assertContains(response, "Ticketkategorien verwalten")
        self.assertContains(response, "Tickets verfolgen")
        self.assertNotContains(response, "Nicht im Sprint")
        for column in ("To Do", "In Progress", "In Review", "Done"):
            self.assertContains(response, column)

    def test_card_shows_priority_as_text_with_priority_class(self):
        self.client.force_login(self.reader)
        response = self.client.get(self.board_url)
        self.assertContains(response, "board-card priority-high")
        self.assertContains(
            response,
            '<span class="card-priority priority-high">Hoch</span>',
            html=False,
        )
        self.assertContains(response, 'class="card-top"')

    def test_board_filters_by_assignee_and_priority(self):
        self.client.force_login(self.reader)
        response = self.client.get(self.board_url, {"assignee": self.editor.pk})
        self.assertContains(response, "Ticketkategorien verwalten")
        self.assertNotContains(response, "E-Mail-Vorlagen")
        response = self.client.get(self.board_url, {"priority": "low"})
        self.assertNotContains(response, "Ticketkategorien verwalten")
        self.assertContains(response, "E-Mail-Vorlagen")

    def test_drag_and_drop_move_is_persisted(self):
        self.client.force_login(self.editor)
        response = self.move(self.item, Status.IN_PROGRESS)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], Status.IN_PROGRESS)
        self.assertEqual(body["version"], self.item.version + 1)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, Status.IN_PROGRESS)
        board = self.client.get(self.board_url)
        column = board.context["columns"][1]
        self.assertEqual(column["status"], Status.IN_PROGRESS)
        self.assertIn(self.item, column["items"])

    def test_form_fallback_move_redirects_to_board(self):
        self.client.force_login(self.editor)
        response = self.move(self.item, Status.IN_REVIEW, as_json=False)
        self.assertRedirects(response, self.board_url)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, Status.IN_REVIEW)

    def test_wip_limit_marks_overfull_column_without_blocking_moves(self):
        self.project.wip_limit_in_progress = 1
        self.project.save()
        self.client.force_login(self.editor)
        self.move(self.item, Status.IN_PROGRESS)
        self.other_item.refresh_from_db()
        response = self.move(self.other_item, Status.IN_PROGRESS)
        self.assertEqual(response.status_code, 200)

        board = self.client.get(self.board_url)
        in_progress = board.context["columns"][1]
        self.assertEqual(in_progress["wip_limit"], 1)
        self.assertTrue(in_progress["over_limit"])
        self.assertContains(board, 'data-wip-limit="1"')
        self.assertIsNone(board.context["columns"][0]["wip_limit"])

    def test_concurrent_move_is_rejected_with_conflict(self):
        self.client.force_login(self.editor)
        stale_version = self.item.version
        self.move(self.item, Status.IN_PROGRESS)
        response = self.move(self.item, Status.DONE, version=stale_version)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["status"], Status.IN_PROGRESS)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, Status.IN_PROGRESS)

    def test_reader_cannot_move_cards(self):
        self.client.force_login(self.reader)
        response = self.move(self.item, Status.DONE)
        self.assertEqual(response.status_code, 403)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, Status.TODO)

    def test_invalid_status_is_rejected(self):
        self.client.force_login(self.editor)
        response = self.move(self.item, "deleted")
        self.assertEqual(response.status_code, 400)

    def test_item_outside_active_sprint_cannot_be_moved(self):
        self.client.force_login(self.editor)
        response = self.move(self.backlog_only, Status.DONE)
        self.assertEqual(response.status_code, 400)

    def test_item_of_foreign_project_cannot_be_moved(self):
        other = make_project("OTHER")
        add_member(other, self.editor)
        foreign = make_item(other)
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse("board:move", args=["HELP"]),
            data=json.dumps(
                {"item": foreign.number + 100, "status": "done", "version": 1}
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_move_requires_csrf_token(self):
        from django.test import Client

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.editor)
        response = csrf_client.post(
            self.move_url,
            data=json.dumps(
                {"item": self.item.number, "status": "done", "version": 1}
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_blocked_items_are_marked(self):
        self.item.is_blocked = True
        self.item.save()
        self.client.force_login(self.reader)
        response = self.client.get(self.board_url)
        self.assertContains(response, "Blockiert")

    def test_board_without_active_sprint_shows_hint(self):
        empty = make_project("EMPTY")
        add_member(empty, self.reader)
        self.client.force_login(self.reader)
        response = self.client.get(reverse("board:board", args=["EMPTY"]))
        self.assertContains(response, "Kein aktiver Sprint")


class LiveBoardTests(TestCase):
    def setUp(self):
        self.project = make_project("LIVE")
        self.editor = make_user()
        self.reader = make_user()
        add_member(self.project, self.editor, access_level=Access.EDIT)
        add_member(self.project, self.reader, access_level=Access.READ)
        self.sprint = make_sprint(self.project)
        self.item = make_item(self.project)
        add_item_to_sprint(self.sprint, self.item, actor=self.editor)
        start_sprint(self.sprint, actor=self.editor)
        self.state_url = reverse("board:state", args=["LIVE"])

    def revision(self):
        return self.client.get(self.state_url).json()["revision"]

    def test_reader_sees_revision_change_after_move_by_someone_else(self):
        self.client.force_login(self.reader)
        board = self.client.get(reverse("board:board", args=["LIVE"]))
        before = self.revision()
        self.assertContains(board, f'data-revision="{before}"')
        self.assertContains(board, f'data-state-url="{self.state_url}"')
        change_item_status(self.item, Status.IN_PROGRESS, actor=self.editor)
        self.assertNotEqual(self.revision(), before)

    def test_move_response_contains_new_revision(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse("board:move", args=["LIVE"]),
            data=json.dumps(
                {"item": self.item.number, "status": "done",
                 "version": self.item.version}
            ),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.json()["revision"], self.revision())

    def test_revision_changes_when_sprint_scope_changes(self):
        self.client.force_login(self.reader)
        before = self.revision()
        add_item_to_sprint(self.sprint, make_item(self.project), actor=self.editor)
        self.assertNotEqual(self.revision(), before)

    def test_outsider_cannot_poll_state(self):
        self.client.force_login(make_user())
        self.assertEqual(self.client.get(self.state_url).status_code, 404)
