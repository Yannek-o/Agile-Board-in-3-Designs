from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.backlog.models import BacklogItem
from apps.projects.models import ProjectMembership
from apps.sprints.services import add_item_to_sprint, start_sprint
from tests.factories import add_member, make_item, make_project, make_sprint, make_user

Access = ProjectMembership.AccessLevel
Type = BacklogItem.ItemType


class SwimlaneTests(TestCase):
    def setUp(self):
        self.project = make_project("LANE")
        self.anna = make_user(first_name="Anna", last_name="A")
        self.bert = make_user(first_name="Bert", last_name="B")
        for user in (self.anna, self.bert):
            add_member(self.project, user, access_level=Access.MANAGE)
        self.epic = make_item(self.project, item_type=Type.EPIC, title="Zahlungen")
        self.anna_item = make_item(
            self.project, title="Annas Karte", assignee=self.anna, priority="high",
            parent=self.epic,
        )
        self.bert_item = make_item(
            self.project, title="Berts Karte", assignee=self.bert, priority="low",
            due_date=timezone.localdate() - timedelta(days=2),
        )
        self.free_item = make_item(self.project, title="Freie Karte", priority="high")
        sprint = make_sprint(self.project)
        for item in (self.anna_item, self.bert_item, self.free_item):
            add_item_to_sprint(sprint, item, actor=self.anna)
        start_sprint(sprint, actor=self.anna)
        self.client.force_login(self.anna)
        self.url = reverse("board:board", args=["LANE"])

    def lanes(self, **params):
        response = self.client.get(self.url, params)
        return response, [
            (lane["label"], [item.title for item in lane["items"]])
            for lane in response.context["lanes"]
        ]

    def test_default_board_has_single_lane(self):
        response, lanes = self.lanes()
        self.assertEqual(response.context["swimlane"], "none")
        self.assertEqual(len(lanes), 1)
        self.assertEqual(len(lanes[0][1]), 3)
        self.assertContains(response, "board-lane")

    def test_lanes_by_assignee_put_unassigned_last(self):
        _, lanes = self.lanes(swimlane="assignee")
        self.assertEqual(
            lanes,
            [
                (self.anna.display_name, ["Annas Karte"]),
                (self.bert.display_name, ["Berts Karte"]),
                ("Nicht zugewiesen", ["Freie Karte"]),
            ],
        )

    def test_lanes_by_epic(self):
        _, lanes = self.lanes(swimlane="epic")
        self.assertEqual(lanes[0], ("Zahlungen", ["Annas Karte"]))
        self.assertEqual(lanes[1][0], "Ohne Epic")
        self.assertCountEqual(lanes[1][1], ["Berts Karte", "Freie Karte"])

    def test_lanes_by_priority_follow_priority_order(self):
        _, lanes = self.lanes(swimlane="priority")
        self.assertEqual([label for label, _ in lanes], ["Hoch", "Niedrig"])

    def test_wip_limit_counts_whole_board_across_lanes(self):
        self.project.wip_limit_in_progress = 2
        self.project.save()
        BacklogItem.objects.filter(project=self.project).exclude(
            item_type=Type.EPIC
        ).update(status=BacklogItem.Status.IN_PROGRESS)
        response = self.client.get(self.url, {"swimlane": "assignee"})
        in_progress_columns = [
            column
            for lane in response.context["lanes"]
            for column in lane["columns"]
            if column["status"] == BacklogItem.Status.IN_PROGRESS
        ]
        self.assertEqual(len(in_progress_columns), 3)
        for column in in_progress_columns:
            self.assertEqual(column["wip_limit"], 2)
            self.assertTrue(column["over_limit"])
            self.assertEqual(column["status_total"], 3)

    def test_quick_filter_mine(self):
        _, lanes = self.lanes(quick="mine")
        self.assertEqual(lanes[0][1], ["Annas Karte"])

    def test_quick_filter_overdue(self):
        _, lanes = self.lanes(quick="overdue")
        self.assertEqual(lanes[0][1], ["Berts Karte"])

    def test_quick_filter_recent_excludes_old_items(self):
        old = timezone.now() - timedelta(days=3)
        BacklogItem.objects.filter(pk=self.bert_item.pk).update(updated_at=old)
        _, lanes = self.lanes(quick="recent")
        self.assertCountEqual(lanes[0][1], ["Annas Karte", "Freie Karte"])

    def test_quick_filters_combine_and_chips_toggle(self):
        response = self.client.get(self.url, {"quick": ["mine", "overdue"]})
        self.assertEqual(
            [lane["items"] for lane in response.context["lanes"]], [[]]
        )
        grouped = self.client.get(
            self.url, {"quick": ["mine", "overdue"], "swimlane": "assignee"}
        )
        self.assertEqual(grouped.context["lanes"], [])
        chips = {chip["key"]: chip for chip in response.context["quick_filters"]}
        self.assertTrue(chips["mine"]["active"])
        self.assertNotIn("quick=mine", chips["mine"]["url"])
        self.assertIn("quick=overdue", chips["mine"]["url"])
        self.assertContains(response, 'role="button" aria-pressed="true"', count=2)
