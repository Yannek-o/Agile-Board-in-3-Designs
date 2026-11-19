from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.activity.models import ActivityEvent
from apps.backlog.models import BacklogItem
from apps.backlog.services import archive_item, change_item_status
from apps.projects.models import ProjectMembership
from apps.reporting.services import sprint_capacity
from apps.sprints.models import Sprint, SprintItem
from apps.sprints.services import (
    SprintError,
    add_item_to_sprint,
    cancel_sprint,
    complete_sprint,
    remove_item_from_sprint,
    start_sprint,
)
from tests.factories import (
    add_member,
    make_item,
    make_project,
    make_sprint,
    make_user,
)

Access = ProjectMembership.AccessLevel
Outcome = SprintItem.Outcome


class SprintServiceTests(TestCase):
    def setUp(self):
        self.project = make_project("HELP")
        self.user = make_user()
        add_member(self.project, self.user, access_level=Access.MANAGE)
        self.sprint = make_sprint(self.project, actor=self.user)

    def test_sprint_numbers_are_sequential_per_project(self):
        second = make_sprint(self.project)
        self.assertEqual(self.sprint.number, 1)
        self.assertEqual(second.number, 2)
        self.assertEqual(str(second), "HELP Sprint 2")

    def test_sprint_must_not_exceed_one_month(self):
        with self.assertRaises(ValidationError):
            make_sprint(
                self.project,
                start_date=date(2026, 11, 1),
                end_date=date(2026, 12, 15),
            )

    def test_end_date_must_not_precede_start(self):
        with self.assertRaises(ValidationError):
            make_sprint(
                self.project,
                start_date=date(2026, 11, 10),
                end_date=date(2026, 11, 9),
            )

    def test_item_is_added_and_removed(self):
        item = make_item(self.project)
        add_item_to_sprint(self.sprint, item, actor=self.user)
        self.assertEqual(list(self.sprint.open_items()), [item])
        remove_item_from_sprint(self.sprint, item, actor=self.user)
        self.assertEqual(list(self.sprint.open_items()), [])
        self.assertEqual(
            SprintItem.objects.get(sprint=self.sprint, item=item).outcome,
            Outcome.REMOVED,
        )

    def test_item_of_other_project_cannot_be_added(self):
        foreign_item = make_item(make_project("OTHER"))
        with self.assertRaises(SprintError):
            add_item_to_sprint(self.sprint, foreign_item, actor=self.user)

    def test_item_cannot_be_in_two_open_sprints(self):
        item = make_item(self.project)
        add_item_to_sprint(self.sprint, item, actor=self.user)
        with self.assertRaises(SprintError):
            add_item_to_sprint(make_sprint(self.project), item, actor=self.user)

    def test_archived_or_done_items_cannot_be_planned(self):
        archived = make_item(self.project)
        archive_item(archived, actor=self.user)
        done = make_item(self.project, status=BacklogItem.Status.DONE)
        for item in (archived, done):
            with self.assertRaises(SprintError):
                add_item_to_sprint(self.sprint, item, actor=self.user)

    def test_only_one_active_sprint_per_project(self):
        start_sprint(self.sprint, actor=self.user)
        second = make_sprint(self.project)
        with self.assertRaises(SprintError):
            start_sprint(second, actor=self.user)
        second.status = Sprint.Status.ACTIVE
        with self.assertRaises(IntegrityError), transaction.atomic():
            second.save()

    def test_sprint_without_goal_cannot_start(self):
        sprint = make_sprint(self.project, goal="")
        with self.assertRaises(SprintError):
            start_sprint(sprint, actor=self.user)

    def test_complete_sprint_carries_unfinished_work_and_keeps_history(self):
        done_item = make_item(self.project, story_points=5)
        open_item = make_item(self.project, story_points=3)
        add_item_to_sprint(self.sprint, done_item, actor=self.user)
        add_item_to_sprint(self.sprint, open_item, actor=self.user)
        start_sprint(self.sprint, actor=self.user)
        change_item_status(done_item, BacklogItem.Status.DONE, actor=self.user)
        next_sprint = make_sprint(self.project)

        complete_sprint(self.sprint, actor=self.user, carry_over_to=next_sprint)

        self.sprint.refresh_from_db()
        self.assertEqual(self.sprint.status, Sprint.Status.COMPLETED)
        self.assertEqual(self.sprint.completed_by, self.user)
        history = {
            entry.item_id: entry
            for entry in SprintItem.objects.filter(sprint=self.sprint)
        }
        self.assertEqual(history[done_item.pk].outcome, Outcome.COMPLETED)
        self.assertEqual(history[done_item.pk].points_at_close, 5)
        self.assertEqual(history[open_item.pk].outcome, Outcome.CARRIED_OVER)
        self.assertEqual(list(next_sprint.open_items()), [open_item])
        self.assertEqual(self.sprint.completed_points(), 5)
        self.assertEqual(self.sprint.committed_points(), 8)
        self.assertTrue(
            ActivityEvent.objects.filter(
                sprint=self.sprint, action=ActivityEvent.Action.SPRINT_COMPLETED
            ).exists()
        )

    def test_complete_sprint_returns_unfinished_work_to_backlog(self):
        open_item = make_item(self.project)
        add_item_to_sprint(self.sprint, open_item, actor=self.user)
        start_sprint(self.sprint, actor=self.user)
        complete_sprint(self.sprint, actor=self.user)
        entry = SprintItem.objects.get(sprint=self.sprint, item=open_item)
        self.assertEqual(entry.outcome, Outcome.RETURNED)
        add_item_to_sprint(make_sprint(self.project), open_item, actor=self.user)

    def test_carry_over_target_must_be_planned_sprint_of_same_project(self):
        start_sprint(self.sprint, actor=self.user)
        foreign = make_sprint(make_project("OTHER"))
        with self.assertRaises(SprintError):
            complete_sprint(self.sprint, actor=self.user, carry_over_to=foreign)

    def test_only_active_sprint_can_be_completed(self):
        with self.assertRaises(SprintError):
            complete_sprint(self.sprint, actor=self.user)

    def test_cancel_sprint_releases_items(self):
        item = make_item(self.project)
        add_item_to_sprint(self.sprint, item, actor=self.user)
        cancel_sprint(self.sprint, actor=self.user)
        self.sprint.refresh_from_db()
        self.assertEqual(self.sprint.status, Sprint.Status.CANCELLED)
        self.assertEqual(
            SprintItem.objects.get(sprint=self.sprint, item=item).outcome,
            Outcome.CANCELLED,
        )

    def test_completed_sprint_cannot_be_modified(self):
        start_sprint(self.sprint, actor=self.user)
        complete_sprint(self.sprint, actor=self.user)
        with self.assertRaises(SprintError):
            add_item_to_sprint(self.sprint, make_item(self.project), actor=self.user)


class SprintViewTests(TestCase):
    def setUp(self):
        self.project = make_project("HELP")
        self.lead = make_user("lead")
        self.editor = make_user("editor")
        add_member(self.project, self.lead, access_level=Access.MANAGE)
        add_member(self.project, self.editor, access_level=Access.EDIT)
        self.sprint = make_sprint(self.project)
        self.item = make_item(self.project, title="Ticketstatus ändern")

    def sprint_url(self, name):
        return reverse(f"sprints:{name}", args=["HELP", self.sprint.number])

    def test_lead_creates_sprint(self):
        self.client.force_login(self.lead)
        response = self.client.post(
            reverse("sprints:create", args=["HELP"]),
            {
                "name": "",
                "goal": "Tickets zuverlässig verfolgen",
                "start_date": "2026-11-30",
                "end_date": "2026-12-11",
            },
        )
        sprint = Sprint.objects.get(project=self.project, number=2)
        self.assertRedirects(
            response, reverse("sprints:detail", args=["HELP", sprint.number])
        )

    def test_invalid_sprint_dates_show_form_errors(self):
        self.client.force_login(self.lead)
        response = self.client.post(
            reverse("sprints:create", args=["HELP"]),
            {"goal": "Ziel", "start_date": "2026-11-30", "end_date": "2027-02-01"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Sprint.objects.filter(number=2).exists())

    def test_planning_page_lists_backlog_and_sprint_backlog(self):
        self.client.force_login(self.editor)
        response = self.client.get(self.sprint_url("detail"))
        self.assertContains(response, "Ticketstatus ändern")
        self.assertContains(response, "Sprint-Ziel")

    def test_planning_actions_require_backlog_rights(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            self.sprint_url("add_item"), {"item": self.item.number}
        )
        self.assertEqual(response.status_code, 403)

    def test_lead_plans_starts_and_completes_sprint(self):
        self.client.force_login(self.lead)
        self.client.post(self.sprint_url("add_item"), {"item": self.item.number})
        self.assertEqual(list(self.sprint.open_items()), [self.item])
        self.client.post(self.sprint_url("start"))
        self.sprint.refresh_from_db()
        self.assertEqual(self.sprint.status, Sprint.Status.ACTIVE)
        response = self.client.post(
            self.sprint_url("complete"), {"carry_over_to": ""}
        )
        self.assertRedirects(response, self.sprint_url("detail"))
        self.sprint.refresh_from_db()
        self.assertEqual(self.sprint.status, Sprint.Status.COMPLETED)

    def test_sprint_list_shows_history(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse("sprints:list", args=["HELP"]))
        self.assertContains(response, "Sprint 1")

    def test_retrospective_is_saved_after_completion_and_shown_in_next_sprint(self):
        next_sprint = make_sprint(self.project)
        retro = {
            "retro_went_well": "Dailys kurz gehalten",
            "retro_to_improve": "Zu viele Tickets in Review",
            "retro_actions": "Review-Limit auf 3 setzen",
        }
        self.client.force_login(self.lead)
        self.assertEqual(
            self.client.post(self.sprint_url("retro"), retro).status_code, 302
        )
        self.sprint.refresh_from_db()
        self.assertEqual(self.sprint.retro_actions, "")

        self.client.post(self.sprint_url("start"))
        self.client.post(self.sprint_url("complete"), {"carry_over_to": ""})
        self.client.post(self.sprint_url("retro"), retro)
        self.sprint.refresh_from_db()
        self.assertEqual(self.sprint.retro_actions, "Review-Limit auf 3 setzen")
        self.assertContains(
            self.client.get(self.sprint_url("detail")), "Dailys kurz gehalten"
        )
        next_page = self.client.get(
            reverse("sprints:detail", args=["HELP", next_sprint.number])
        )
        self.assertContains(next_page, "Review-Limit auf 3 setzen")

    def test_retrospective_requires_backlog_rights(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            self.sprint_url("retro"), {"retro_actions": "x"}
        )
        self.assertEqual(response.status_code, 403)

    def complete_sprint_with_done_points(self, points: int) -> None:
        sprint = make_sprint(self.project)
        item = make_item(self.project, story_points=points)
        add_item_to_sprint(sprint, item, actor=self.lead)
        start_sprint(sprint, actor=self.lead)
        change_item_status(item, BacklogItem.Status.DONE, actor=self.lead)
        complete_sprint(sprint, actor=self.lead)

    def test_capacity_compares_planned_points_with_recent_velocity(self):
        for points in (2, 8, 10, 12):
            self.complete_sprint_with_done_points(points)
        planned = make_sprint(self.project)
        add_item_to_sprint(
            planned, make_item(self.project, story_points=13), actor=self.lead
        )
        capacity = sprint_capacity(planned)
        self.assertEqual(capacity["velocity"], 10)
        self.assertEqual(capacity["sprints"], 3)
        self.assertEqual(capacity["planned"], 13)
        self.assertTrue(capacity["over"])
        self.client.force_login(self.lead)
        page = self.client.get(
            reverse("sprints:detail", args=["HELP", planned.number])
        )
        self.assertContains(page, "Ø letzte 3 Sprints: 10 SP")

    def test_capacity_is_unknown_without_completed_sprints(self):
        capacity = sprint_capacity(self.sprint)
        self.assertIsNone(capacity["velocity"])
        self.assertFalse(capacity["over"])

    def test_outsider_cannot_open_sprint(self):
        self.client.force_login(make_user())
        self.assertEqual(self.client.get(self.sprint_url("detail")).status_code, 404)
