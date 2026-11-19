from datetime import date, datetime, time

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.activity.models import ActivityEvent
from apps.backlog.models import BacklogItem
from apps.backlog.services import change_item_status
from apps.projects.models import ProjectMembership
from apps.reporting.charts import cumulative_flow, sprint_burnup, velocity_chart
from apps.sprints.services import add_item_to_sprint, complete_sprint, start_sprint
from tests.factories import add_member, make_item, make_project, make_sprint, make_user

Access = ProjectMembership.AccessLevel
Status = BacklogItem.Status


def moment(day: date, hour: int = 10):
    return timezone.make_aware(datetime.combine(day, time(hour, 0)))


class ChartTestCase(TestCase):
    def setUp(self):
        self.project = make_project("CHT")
        self.user = make_user()
        add_member(self.project, self.user, access_level=Access.MANAGE)

    def change_status_on(self, item, status, day):
        change_item_status(item, status, actor=self.user)
        event = ActivityEvent.objects.filter(
            item=item, action=ActivityEvent.Action.STATUS_CHANGED
        ).latest("pk")
        ActivityEvent.objects.filter(pk=event.pk).update(created_at=moment(day))

    def created_on(self, item, day):
        BacklogItem.objects.filter(pk=item.pk).update(created_at=moment(day, 8))


class VelocityChartTests(ChartTestCase):
    def finish_sprint(self, committed: int, done: int):
        sprint = make_sprint(self.project)
        finished = make_item(self.project, story_points=done)
        add_item_to_sprint(sprint, finished, actor=self.user)
        if committed > done:
            open_item = make_item(self.project, story_points=committed - done)
            add_item_to_sprint(sprint, open_item, actor=self.user)
        start_sprint(sprint, actor=self.user)
        change_item_status(finished, Status.DONE, actor=self.user)
        complete_sprint(sprint, actor=self.user)

    def test_no_completed_sprints_means_no_chart(self):
        self.assertIsNone(velocity_chart(self.project))

    def test_bars_in_chronological_order_with_average(self):
        self.finish_sprint(committed=8, done=5)
        self.finish_sprint(committed=8, done=8)
        chart = velocity_chart(self.project)
        self.assertEqual(
            [(bar["committed"], bar["completed"]) for bar in chart["bars"]],
            [(8, 5), (8, 8)],
        )
        self.assertEqual(chart["average"], 6.5)
        self.assertTrue(all(bar["completed_height"] > 0 for bar in chart["bars"]))


class BurnupTests(ChartTestCase):
    def test_scope_and_done_lines(self):
        sprint = make_sprint(
            self.project, start_date=date(2026, 11, 16), end_date=date(2026, 11, 29)
        )
        first = make_item(self.project, story_points=5)
        second = make_item(self.project, story_points=3)
        add_item_to_sprint(sprint, first, actor=self.user)
        add_item_to_sprint(sprint, second, actor=self.user)
        start_sprint(sprint, actor=self.user)
        type(sprint).objects.filter(pk=sprint.pk).update(
            started_at=moment(date(2026, 11, 16), 8)
        )
        sprint.entries.update(added_at=moment(date(2026, 11, 16), 7))
        sprint.refresh_from_db()
        self.change_status_on(first, Status.DONE, date(2026, 11, 17))
        late = make_item(self.project, story_points=2)
        entry = add_item_to_sprint(sprint, late, actor=self.user)
        type(entry).objects.filter(pk=entry.pk).update(
            added_at=moment(date(2026, 11, 18), 9)
        )
        chart = sprint_burnup(sprint, today=date(2026, 11, 19))
        rows = [(row["scope"], row["done"]) for row in chart["rows"][:4]]
        self.assertEqual(rows, [(8, 0), (8, 5), (10, 5), (10, 5)])
        self.assertIsNone(chart["rows"][4]["done"])

    def test_not_started_sprint_has_no_burnup(self):
        self.assertIsNone(sprint_burnup(make_sprint(self.project)))


class CumulativeFlowTests(ChartTestCase):
    def test_items_per_status_and_day(self):
        waiting = make_item(self.project)
        working = make_item(self.project)
        finished = make_item(self.project)
        self.created_on(waiting, date(2026, 11, 17))
        self.created_on(working, date(2026, 11, 17))
        self.created_on(finished, date(2026, 11, 19))
        self.change_status_on(working, Status.IN_PROGRESS, date(2026, 11, 19))
        self.change_status_on(finished, Status.DONE, date(2026, 11, 20))
        flow = cumulative_flow(self.project, days=3, today=date(2026, 11, 20))
        counts = [
            (row["counts"]["todo"], row["counts"]["in_progress"], row["counts"]["done"])
            for row in flow["rows"]
        ]
        self.assertEqual(counts, [(2, 0, 0), (2, 1, 0), (1, 1, 1)])
        self.assertEqual(
            [band["status"] for band in flow["bands"]],
            ["done", "in_review", "in_progress", "todo"],
        )

    def test_young_projects_start_at_first_item_but_show_a_week(self):
        item = make_item(self.project)
        self.created_on(item, date(2026, 11, 18))
        flow = cumulative_flow(self.project, today=date(2026, 11, 20))
        self.assertEqual(len(flow["rows"]), 7)
        self.created_on(item, date(2026, 11, 1))
        flow = cumulative_flow(self.project, today=date(2026, 11, 20))
        self.assertEqual(len(flow["rows"]), 20)

    def test_archived_items_are_ignored(self):
        item = make_item(self.project)
        BacklogItem.objects.filter(pk=item.pk).update(archived_at=timezone.now())
        flow = cumulative_flow(self.project, days=2)
        self.assertEqual(flow["rows"][-1]["total"], 0)


class ReportPageTests(ChartTestCase):
    def test_report_page_shows_charts(self):
        make_item(self.project)
        self.client.force_login(self.user)
        response = self.client.get(reverse("reporting:project_report", args=["CHT"]))
        self.assertContains(response, "Cumulative Flow")
        self.assertContains(response, "Velocity")
        self.assertContains(response, 'class="chart cfd"')
