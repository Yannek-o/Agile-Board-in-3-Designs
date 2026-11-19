from django.test import TestCase
from django.urls import reverse

from apps.backlog.models import BacklogItem
from apps.backlog.services import change_item_status
from apps.projects.models import ProjectMembership
from apps.reporting.sprint_report import sprint_report
from apps.sprints.services import (
    add_item_to_sprint,
    complete_sprint,
    remove_item_from_sprint,
    start_sprint,
)
from tests.factories import add_member, make_item, make_project, make_sprint, make_user

Access = ProjectMembership.AccessLevel
Status = BacklogItem.Status


class SprintReportTests(TestCase):
    def setUp(self):
        self.project = make_project("REP")
        self.lead = make_user()
        add_member(self.project, self.lead, access_level=Access.MANAGE)
        self.sprint = make_sprint(self.project)
        self.done = make_item(self.project, title="Fertig", story_points=5)
        self.open = make_item(self.project, title="Offen", story_points=3)
        self.dropped = make_item(self.project, title="Gestrichen", story_points=2)
        for item in (self.done, self.open, self.dropped):
            add_item_to_sprint(self.sprint, item, actor=self.lead)
        start_sprint(self.sprint, actor=self.lead)
        self.late = make_item(self.project, title="Nachgereicht", story_points=8)
        add_item_to_sprint(self.sprint, self.late, actor=self.lead)
        remove_item_from_sprint(self.sprint, self.dropped, actor=self.lead)
        change_item_status(self.done, Status.DONE, actor=self.lead)
        self.sprint.refresh_from_db()

    def titles(self, rows):
        return [row["item"].title for row in rows]

    def test_not_started_sprint_has_no_report(self):
        self.assertIsNone(sprint_report(make_sprint(self.project)))

    def test_open_sprint_groups_entries(self):
        report = sprint_report(self.sprint)
        self.assertEqual(self.titles(report["completed"]), ["Fertig"])
        self.assertCountEqual(
            self.titles(report["not_completed"]), ["Offen", "Nachgereicht"]
        )
        self.assertEqual(self.titles(report["added"]), ["Nachgereicht"])
        self.assertEqual(self.titles(report["removed"]), ["Gestrichen"])

    def test_points_summary(self):
        summary = sprint_report(self.sprint)["summary"]
        self.assertEqual(summary["committed_at_start"], 10)
        self.assertEqual(summary["added"], 8)
        self.assertEqual(summary["removed"], 2)
        self.assertEqual(summary["final_scope"], 16)
        self.assertEqual(summary["completed"], 5)
        self.assertEqual(summary["percent"], 31)

    def test_completed_sprint_uses_outcomes(self):
        complete_sprint(self.sprint, actor=self.lead)
        self.sprint.refresh_from_db()
        report = sprint_report(self.sprint)
        self.assertEqual(self.titles(report["completed"]), ["Fertig"])
        self.assertCountEqual(
            self.titles(report["not_completed"]), ["Offen", "Nachgereicht"]
        )
        self.assertEqual(report["summary"]["completed"], 5)

    def test_report_is_shown_on_sprint_page(self):
        self.client.force_login(self.lead)
        response = self.client.get(
            reverse("sprints:detail", args=["REP", self.sprint.number])
        )
        self.assertContains(response, "Sprint-Bericht")
        self.assertContains(response, "Nach dem Start hinzugefügt")
        self.assertContains(response, "Nachgereicht")
