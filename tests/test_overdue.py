from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.backlog.models import BacklogItem
from apps.backlog.services import change_item_status
from apps.projects.models import ProjectMembership
from apps.sprints.services import add_item_to_sprint, start_sprint
from tests.factories import add_member, make_item, make_project, make_sprint, make_user

Access = ProjectMembership.AccessLevel
Status = BacklogItem.Status


def days_from_today(days: int):
    return timezone.localdate() + timedelta(days=days)


class OverdueItemTests(TestCase):
    def setUp(self):
        self.project = make_project("LATE")
        self.user = make_user()
        add_member(self.project, self.user, access_level=Access.MANAGE)

    def test_open_item_past_due_date_is_overdue(self):
        item = make_item(self.project, due_date=days_from_today(-1))
        self.assertTrue(item.is_overdue)

    def test_item_due_today_or_later_is_not_overdue(self):
        due_today = make_item(self.project, due_date=days_from_today(0))
        due_later = make_item(self.project, due_date=days_from_today(3))
        self.assertFalse(due_today.is_overdue)
        self.assertFalse(due_later.is_overdue)

    def test_item_without_due_date_is_not_overdue(self):
        self.assertFalse(make_item(self.project).is_overdue)

    def test_done_item_is_not_overdue(self):
        item = make_item(self.project, due_date=days_from_today(-5))
        sprint = make_sprint(self.project, start_date=days_from_today(-3))
        add_item_to_sprint(sprint, item, actor=self.user)
        start_sprint(sprint, actor=self.user)
        item = change_item_status(item, Status.DONE, actor=self.user)
        self.assertFalse(item.is_overdue)


class OverdueBoardTests(TestCase):
    def setUp(self):
        self.project = make_project("LATE")
        self.user = make_user()
        add_member(self.project, self.user, access_level=Access.MANAGE)
        self.client.force_login(self.user)

    def start_sprint_with(self, *items, start_offset=-3, end_offset=10):
        sprint = make_sprint(
            self.project,
            start_date=days_from_today(start_offset),
            end_date=days_from_today(end_offset),
        )
        for item in items:
            add_item_to_sprint(sprint, item, actor=self.user)
        start_sprint(sprint, actor=self.user)
        sprint.refresh_from_db()
        return sprint

    def test_overdue_card_is_highlighted_with_text(self):
        late = make_item(self.project, title="Spaet", due_date=days_from_today(-2))
        on_time = make_item(self.project, title="Puenktlich")
        self.start_sprint_with(late, on_time)
        response = self.client.get(reverse("board:board", args=["LATE"]))
        self.assertContains(response, " overdue", count=1)
        self.assertContains(response, "Überfällig seit")

    def test_sprint_past_end_date_is_marked_overdue(self):
        sprint = self.start_sprint_with(
            make_item(self.project), start_offset=-14, end_offset=-1
        )
        self.assertTrue(sprint.is_overdue)
        response = self.client.get(reverse("board:board", args=["LATE"]))
        self.assertContains(response, "Sprint überfällig")

    def test_running_sprint_is_not_overdue(self):
        sprint = self.start_sprint_with(make_item(self.project))
        self.assertFalse(sprint.is_overdue)
        response = self.client.get(reverse("board:board", args=["LATE"]))
        self.assertNotContains(response, "Sprint überfällig")
        self.assertNotContains(response, "board-card overdue")


class OverdueProjectListTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.late = make_project("LATE")
        self.fine = make_project("FINE")
        for project in (self.late, self.fine):
            add_member(project, self.user, access_level=Access.MANAGE)
        self.client.force_login(self.user)

    def test_project_with_overdue_item_is_marked(self):
        make_item(self.late, due_date=days_from_today(-1))
        make_item(self.fine, due_date=days_from_today(5))
        response = self.client.get(reverse("projects:list"))
        projects = {p.key: p for p in response.context["projects"]}
        self.assertTrue(projects["LATE"].is_delayed)
        self.assertFalse(projects["FINE"].is_delayed)
        self.assertContains(response, "project-card overdue", count=1)
        self.assertContains(response, "In Verzug", count=1)

    def test_project_with_overdue_active_sprint_is_marked(self):
        sprint = make_sprint(
            self.fine, start_date=days_from_today(-14), end_date=days_from_today(-1)
        )
        start_sprint(sprint, actor=self.user)
        response = self.client.get(reverse("projects:list"))
        projects = {p.key: p for p in response.context["projects"]}
        self.assertTrue(projects["FINE"].is_delayed)
