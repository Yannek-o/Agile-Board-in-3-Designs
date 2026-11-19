from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.backlog.models import BacklogItem
from apps.projects.models import ProjectMembership
from apps.reporting.kpis import (
    SNAPSHOT_RETENTION_DAYS,
    kpi_tiles,
    record_dashboard_snapshot,
)
from apps.reporting.models import DashboardSnapshot
from tests.factories import add_member, make_item, make_project, make_user

Access = ProjectMembership.AccessLevel

TODAY = date(2026, 11, 19)


def metrics(**overrides) -> dict:
    values = {
        "active_projects": 1,
        "running_sprints": 1,
        "my_open_items": 2,
        "high_priority_open": 0,
        "blocked_items": 0,
        "sprint_done": 1,
        "sprint_total": 3,
    }
    values.update(overrides)
    return values


def snapshot(user, days_ago: int, **overrides) -> DashboardSnapshot:
    return DashboardSnapshot.objects.create(
        user=user, day=TODAY - timedelta(days=days_ago), metrics=metrics(**overrides)
    )


def tiles_by_key(user, current: dict) -> dict:
    return {tile["key"]: tile for tile in kpi_tiles(user, current, today=TODAY)}


class SnapshotRecordingTests(TestCase):
    def setUp(self):
        self.user = make_user("ben")

    def test_one_snapshot_per_user_and_day_holds_the_latest_values(self):
        record_dashboard_snapshot(self.user, metrics(blocked_items=1), today=TODAY)
        record_dashboard_snapshot(self.user, metrics(blocked_items=3), today=TODAY)
        snapshots = DashboardSnapshot.objects.filter(user=self.user)
        self.assertEqual(snapshots.count(), 1)
        self.assertEqual(snapshots.get().metrics["blocked_items"], 3)

    def test_snapshots_beyond_the_retention_period_are_removed(self):
        snapshot(self.user, SNAPSHOT_RETENTION_DAYS + 1)
        kept = snapshot(self.user, SNAPSHOT_RETENTION_DAYS)
        record_dashboard_snapshot(self.user, metrics(), today=TODAY)
        days = set(
            DashboardSnapshot.objects.filter(user=self.user).values_list(
                "day", flat=True
            )
        )
        self.assertEqual(days, {kept.day, TODAY})

    def test_viewing_the_dashboard_records_todays_values(self):
        project = make_project("HELP")
        add_member(project, self.user, access_level=Access.MANAGE)
        make_item(project, assignee=self.user, is_blocked=True)
        self.client.force_login(self.user)
        self.client.get(reverse("reporting:dashboard"))
        recorded = DashboardSnapshot.objects.get(
            user=self.user, day=timezone.localdate()
        )
        self.assertEqual(recorded.metrics["blocked_items"], 1)
        self.assertEqual(recorded.metrics["my_open_items"], 1)


class TrendTests(TestCase):
    def setUp(self):
        self.user = make_user("ben")

    def test_trend_compares_with_the_value_from_one_week_ago(self):
        snapshot(self.user, 9, blocked_items=5)
        snapshot(self.user, 7, blocked_items=0)
        snapshot(self.user, 2, blocked_items=4)
        trend = tiles_by_key(self.user, metrics(blocked_items=2))["blocked_items"][
            "trend"
        ]
        self.assertEqual(trend["delta"], 2)
        self.assertEqual(trend["display"], "+2")
        self.assertEqual(trend["since"], TODAY - timedelta(days=7))
        self.assertEqual(trend["tone"], "danger")

    def test_young_history_compares_with_the_oldest_snapshot(self):
        snapshot(self.user, 3, sprint_done=0)
        snapshot(self.user, 1, sprint_done=1)
        trend = tiles_by_key(self.user, metrics(sprint_done=2))["sprint_done"][
            "trend"
        ]
        self.assertEqual(trend["delta"], 2)
        self.assertEqual(trend["since"], TODAY - timedelta(days=3))
        self.assertEqual(trend["tone"], "success")

    def test_fewer_problems_are_shown_as_improvement(self):
        snapshot(self.user, 7, high_priority_open=4)
        trend = tiles_by_key(self.user, metrics(high_priority_open=1))[
            "high_priority_open"
        ]["trend"]
        self.assertEqual(trend["display"], "−3")
        self.assertEqual(trend["tone"], "success")

    def test_unchanged_and_neutral_metrics_have_no_tone(self):
        snapshot(self.user, 7, my_open_items=2, active_projects=1)
        tiles = tiles_by_key(self.user, metrics(my_open_items=2, active_projects=3))
        self.assertEqual(tiles["my_open_items"]["trend"]["display"], "±0")
        self.assertEqual(tiles["my_open_items"]["trend"]["tone"], "neutral")
        self.assertEqual(tiles["active_projects"]["trend"]["tone"], "neutral")

    def test_without_history_there_is_no_trend_and_no_sparkline(self):
        snapshot(self.user, 0)
        tile = tiles_by_key(self.user, metrics())["blocked_items"]
        self.assertIsNone(tile["trend"])
        self.assertIsNone(tile["sparkline"])

    def test_other_users_history_is_ignored(self):
        snapshot(make_user("andere"), 7, blocked_items=9)
        self.assertIsNone(tiles_by_key(self.user, metrics())["blocked_items"]["trend"])


class SparklineTests(TestCase):
    def setUp(self):
        self.user = make_user("ben")

    def test_sparkline_has_one_point_per_known_day_of_the_last_two_weeks(self):
        snapshot(self.user, 20, blocked_items=7)
        snapshot(self.user, 13, blocked_items=0)
        snapshot(self.user, 6, blocked_items=4)
        sparkline = tiles_by_key(self.user, metrics(blocked_items=2))[
            "blocked_items"
        ]["sparkline"]
        self.assertEqual(
            sparkline["points"], "0.0,26.0 53.8,2.0 100.0,14.0"
        )
        self.assertEqual(sparkline["last_x"], "100.0")
        self.assertEqual(sparkline["last_y"], "14.0")

    def test_constant_values_draw_a_flat_line(self):
        snapshot(self.user, 4, running_sprints=1)
        sparkline = tiles_by_key(self.user, metrics(running_sprints=1))[
            "running_sprints"
        ]["sparkline"]
        self.assertEqual(sparkline["points"], "69.2,14.0 100.0,14.0")


class TileRenderingTests(TestCase):
    def setUp(self):
        self.user = make_user("ben")
        self.project = make_project("HELP")
        add_member(self.project, self.user, access_level=Access.MANAGE)
        make_item(self.project, is_blocked=True, priority=BacklogItem.Priority.HIGH)

    def test_signal_colours_mark_tiles_that_need_attention(self):
        tiles = tiles_by_key(self.user, metrics(blocked_items=1, high_priority_open=2))
        self.assertEqual(tiles["blocked_items"]["signal"], "danger")
        self.assertEqual(tiles["high_priority_open"]["signal"], "warning")
        self.assertIsNone(tiles["my_open_items"]["signal"])
        done = tiles_by_key(self.user, metrics(sprint_done=3, sprint_total=3))
        self.assertEqual(done["sprint_done"]["signal"], "success")
        self.assertEqual(done["sprint_done"]["value"], "3 / 3")

    def test_dashboard_renders_icon_trend_and_sparkline(self):
        week_ago = timezone.localdate() - timedelta(days=7)
        DashboardSnapshot.objects.create(
            user=self.user, day=week_ago, metrics=metrics(blocked_items=0)
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("reporting:dashboard"))
        self.assertContains(
            response, 'class="ab-tile tile-button kpi-tile signal-danger'
        )
        self.assertContains(response, 'class="kpi-icon"', count=6)
        self.assertContains(response, 'class="kpi-sparkline"')
        self.assertContains(
            response, f"+1</span> seit {week_ago:%d.%m.}", html=False
        )
