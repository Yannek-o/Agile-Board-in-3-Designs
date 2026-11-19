from datetime import date, datetime, time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone, translation

from apps.activity.models import ActivityEvent
from apps.backlog.models import BacklogItem
from apps.backlog.services import change_item_status
from apps.projects.models import Project, ProjectMembership
from apps.reporting.burndown import sprint_burndown
from apps.reporting.services import sprint_point_breakdowns
from apps.sprints.models import SprintItem
from apps.sprints.services import (
    add_item_to_sprint,
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
Status = BacklogItem.Status


class DashboardTests(TestCase):
    def setUp(self):
        self.user = make_user("ben", first_name="Ben")
        self.project = make_project("HELP", name="Internal Helpdesk")
        add_member(self.project, self.user, access_level=Access.MANAGE)
        planned = make_project("PLAN", status=Project.Status.PLANNED)
        add_member(planned, self.user)
        self.sprint = make_sprint(self.project)
        self.items = [
            make_item(self.project, assignee=self.user, title="Meine Aufgabe 1",
                      priority=BacklogItem.Priority.HIGH),
            make_item(self.project, assignee=self.user, title="Meine Aufgabe 2",
                      is_blocked=True),
            make_item(self.project, title="Fremde Aufgabe"),
        ]
        for item in self.items:
            add_item_to_sprint(self.sprint, item, actor=self.user)
        start_sprint(self.sprint, actor=self.user)
        change_item_status(self.items[2], Status.DONE, actor=self.user)
        secret = make_project("SECRET", name="Geheim")
        make_item(secret, title="Geheime Aufgabe",
                  priority=BacklogItem.Priority.CRITICAL)

    def test_dashboard_metrics_are_computed_from_database(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("reporting:dashboard"))
        metrics = response.context["metrics"]
        self.assertEqual(metrics["active_projects"], 1)
        self.assertEqual(metrics["running_sprints"], 1)
        self.assertEqual(metrics["my_open_items"], 2)
        self.assertEqual(metrics["high_priority_open"], 1)
        self.assertEqual(metrics["blocked_items"], 1)
        self.assertEqual(metrics["sprint_done"], 1)
        self.assertEqual(metrics["sprint_total"], 3)
        self.assertContains(response, "Meine Aufgabe 1")
        self.assertContains(response, "Internal Helpdesk")
        self.assertNotContains(response, "Geheime Aufgabe")

    def test_sprint_progress_is_shown(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("reporting:dashboard"))
        progress = response.context["active_sprints"][0]
        self.assertEqual(progress["done"], 1)
        self.assertEqual(progress["total"], 3)
        self.assertEqual(progress["percent"], 33)

    def test_recently_changed_items_are_listed(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("reporting:dashboard"))
        recent = list(response.context["recent_items"])
        self.assertEqual(recent[0], self.items[2])

    def test_metric_details_list_exactly_the_counted_entries(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("reporting:dashboard"))
        details = response.context["metric_details"]
        self.assertEqual(list(details["active_projects"]), [self.project])
        self.assertCountEqual(details["my_open_items"], self.items[:2])
        self.assertEqual(list(details["high_priority_open"]), [self.items[0]])
        self.assertEqual(list(details["blocked_items"]), [self.items[1]])
        self.assertEqual(list(details["sprint_done"]), [self.items[2]])
        self.assertContains(response, 'id="metric-blocked_items"')
        self.assertNotContains(response, "Geheime Aufgabe")

    def test_dashboard_notes_are_saved_per_user(self):
        notes_url = reverse("reporting:dashboard_notes")
        self.client.force_login(self.user)
        response = self.client.post(
            notes_url, {"notes": "  Retro vorbereiten\nDemo am Freitag  "},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.json(), {"saved": True})
        self.user.refresh_from_db()
        self.assertEqual(
            self.user.dashboard_notes, "Retro vorbereiten\nDemo am Freitag"
        )
        self.assertContains(
            self.client.get(reverse("reporting:dashboard")), "Demo am Freitag"
        )
        other = make_user("andere")
        self.client.force_login(other)
        self.assertNotContains(
            self.client.get(reverse("reporting:dashboard")), "Demo am Freitag"
        )
        self.assertEqual(self.client.get(notes_url).status_code, 405)


class SprintPointBreakdownTests(TestCase):
    def setUp(self):
        self.user = make_user("lead")
        self.project = make_project("HELP")
        add_member(self.project, self.user, access_level=Access.MANAGE)
        today = timezone.localdate()
        self.sprint = make_sprint(
            self.project, start_date=today, end_date=today + timedelta(days=9)
        )
        self.todo = make_item(self.project, story_points=5)
        self.in_progress = make_item(self.project, story_points=3)
        self.done = make_item(self.project, story_points=2)
        self.removed = make_item(self.project, story_points=8)
        unestimated = make_item(self.project)
        for item in (self.todo, self.in_progress, self.done, self.removed,
                     unestimated):
            add_item_to_sprint(self.sprint, item, actor=self.user)
        remove_item_from_sprint(self.sprint, self.removed, actor=self.user)
        start_sprint(self.sprint, actor=self.user)
        change_item_status(self.in_progress, Status.IN_PROGRESS, actor=self.user)
        change_item_status(self.done, Status.DONE, actor=self.user)

    def segments(self):
        self.sprint.refresh_from_db()
        breakdown = sprint_point_breakdowns([self.sprint])[self.sprint.pk]
        return breakdown, [
            (segment["status"], segment["points"])
            for segment in breakdown["segments"]
        ]

    def test_open_sprint_sums_current_points_per_status(self):
        breakdown, segments = self.segments()
        self.assertEqual(
            segments, [("todo", 5), ("in_progress", 3), ("done", 2)]
        )
        self.assertEqual(breakdown["done"], 2)
        self.assertEqual(breakdown["total"], 10)
        self.assertEqual(breakdown["percent"], 20)
        self.assertEqual(breakdown["days_left"], 9)

    def test_closed_sprint_uses_snapshot_taken_at_completion(self):
        complete_sprint(self.sprint, actor=self.user)
        change_item_status(self.todo, Status.DONE, actor=self.user)
        breakdown, segments = self.segments()
        self.assertEqual(
            segments, [("todo", 5), ("in_progress", 3), ("done", 2)]
        )
        self.assertIsNone(breakdown["days_left"])

    def test_sprint_list_shows_progress_bar(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("sprints:list", args=["HELP"]))
        self.assertContains(response, "2/10 SP")
        self.assertContains(response, "noch 9 Tage")
        self.assertContains(response, 'data-status="in_progress"')


class ReportAndActivityTests(TestCase):
    def setUp(self):
        self.project = make_project("HELP")
        self.member = make_user()
        add_member(self.project, self.member)
        self.item = make_item(self.project, actor=self.member, title="Alpha")

    def test_project_report_is_visible_for_members_only(self):
        url = reverse("reporting:project_report", args=["HELP"])
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(make_user())
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_activity_log_lists_project_events_only(self):
        other = make_project("OTHER")
        make_item(other, title="Fremd")
        self.client.force_login(self.member)
        response = self.client.get(reverse("activity:list", args=["HELP"]))
        events = list(response.context["events"])
        self.assertTrue(events)
        self.assertTrue(all(event.project == self.project for event in events))
        self.assertEqual(events[0].action, ActivityEvent.Action.CREATED)


class NavigationTests(TestCase):
    def test_section_shortcut_uses_last_visited_project(self):
        user = make_user()
        make_project("ALPHA")
        add_member(make_project("ALPHA2"), user)
        project = make_project("HELP")
        add_member(project, user)
        self.client.force_login(user)
        self.client.get(reverse("projects:detail", args=["HELP"]))
        response = self.client.get(reverse("core:go", args=["board"]))
        self.assertRedirects(
            response, reverse("board:board", args=["HELP"]),
            fetch_redirect_response=False,
        )

    def test_without_last_project_the_one_with_active_sprint_opens(self):
        user = make_user()
        add_member(make_project("ALPHA"), user)
        project = make_project("HELP")
        add_member(project, user, access_level=Access.MANAGE)
        sprint = make_sprint(project)
        add_item_to_sprint(sprint, make_item(project), actor=user)
        start_sprint(sprint, actor=user)
        self.client.force_login(user)
        response = self.client.get(reverse("core:go", args=["backlog"]))
        self.assertRedirects(
            response, reverse("backlog:planning", args=["HELP"]),
            fetch_redirect_response=False,
        )

    def test_without_any_active_project_the_project_list_is_shown(self):
        user = make_user()
        add_member(make_project("PLAN", status=Project.Status.PLANNED), user)
        self.client.force_login(user)
        response = self.client.get(reverse("core:go", args=["board"]))
        self.assertRedirects(response, reverse("projects:list") + "?section=board")

    def test_unknown_section_returns_404(self):
        self.client.force_login(make_user())
        response = self.client.get(reverse("core:go", args=["unknown"]))
        self.assertEqual(response.status_code, 404)


class BurndownTests(TestCase):
    def setUp(self):
        self.project = make_project("BURN")
        self.user = make_user()
        add_member(self.project, self.user, access_level=Access.MANAGE)
        self.sprint = make_sprint(
            self.project, start_date=date(2026, 11, 16),
            end_date=date(2026, 11, 29),
        )
        self.item_a = make_item(self.project, story_points=5)
        self.item_b = make_item(self.project, story_points=3)
        add_item_to_sprint(self.sprint, self.item_a, actor=self.user)
        add_item_to_sprint(self.sprint, self.item_b, actor=self.user)
        start_sprint(self.sprint, actor=self.user)
        self.sprint.refresh_from_db()

    def change_status_on(self, item, status, day):
        change_item_status(item, status, actor=self.user)
        event = ActivityEvent.objects.filter(
            item=item, action=ActivityEvent.Action.STATUS_CHANGED
        ).latest("pk")
        moment = timezone.make_aware(datetime.combine(day, time(10, 0)))
        ActivityEvent.objects.filter(pk=event.pk).update(created_at=moment)

    def test_remaining_points_follow_status_history_and_scope(self):
        self.change_status_on(self.item_a, Status.DONE, date(2026, 11, 17))
        self.change_status_on(self.item_b, Status.DONE, date(2026, 11, 18))
        self.change_status_on(self.item_b, Status.IN_PROGRESS, date(2026, 11, 19))
        late_item = make_item(self.project, story_points=2)
        entry = add_item_to_sprint(self.sprint, late_item, actor=self.user)
        late_moment = timezone.make_aware(datetime(2026, 11, 19, 9, 0))
        SprintItem.objects.filter(pk=entry.pk).update(added_at=late_moment)

        burndown = sprint_burndown(self.sprint, today=date(2026, 11, 20))

        actual = {row["day"]: row["remaining"] for row in burndown["rows"]}
        self.assertEqual(actual[date(2026, 11, 16)], 8)
        self.assertEqual(actual[date(2026, 11, 17)], 3)
        self.assertEqual(actual[date(2026, 11, 18)], 0)
        self.assertEqual(actual[date(2026, 11, 19)], 5)
        self.assertEqual(actual[date(2026, 11, 20)], 5)
        self.assertIsNone(actual[date(2026, 11, 21)])
        self.assertEqual(burndown["rows"][0]["ideal"], 8)
        self.assertEqual(burndown["rows"][-1]["ideal"], 0)
        self.assertTrue(burndown["actual_points"])

    def test_planned_sprint_has_no_burndown(self):
        planned = make_sprint(self.project)
        self.assertIsNone(sprint_burndown(planned))

    def test_chart_has_round_gridlines_today_marker_and_day_points(self):
        self.change_status_on(self.item_a, Status.DONE, date(2026, 11, 17))
        burndown = sprint_burndown(self.sprint, today=date(2026, 11, 20))

        grid_values = [line["value"] for line in burndown["gridlines"]]
        self.assertEqual(grid_values, [0, 2, 4, 6, 8])
        self.assertEqual(burndown["max_value"], 8)
        day_points = burndown["day_points"]
        self.assertEqual(len(day_points), 5)
        self.assertEqual(day_points[1]["remaining"], 3)
        self.assertEqual(burndown["today_x"], day_points[4]["x"])
        self.assertTrue(burndown["area_points"].endswith(
            f"{day_points[4]['x']},{burndown['plot_bottom']}"
        ))
        self.assertEqual(burndown["plan_delta"], -2.5)

    def test_closed_or_finished_sprint_has_no_today_marker(self):
        burndown = sprint_burndown(self.sprint, today=date(2026, 12, 5))
        self.assertIsNone(burndown["today_x"])

    def test_burndown_is_shown_on_sprint_page_and_report(self):
        self.client.force_login(self.user)
        sprint_page = self.client.get(
            reverse("sprints:detail", args=["BURN", self.sprint.number])
        )
        self.assertContains(sprint_page, "Burndown")
        self.assertContains(sprint_page, "<svg")
        report = self.client.get(reverse("reporting:project_report", args=["BURN"]))
        self.assertContains(report, "Burndown")

    def test_chart_coordinates_ignore_german_number_format(self):
        self.client.force_login(self.user)
        with translation.override("de"):
            sprint_page = self.client.get(
                reverse("sprints:detail", args=["BURN", self.sprint.number])
            )
        self.assertContains(sprint_page, '<circle class="marker" cx="40.0"')
        self.assertNotRegex(sprint_page.content.decode(), r'c[xy]="\d+,\d')
