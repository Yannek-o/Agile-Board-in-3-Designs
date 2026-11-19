from django.test import TestCase
from django.urls import reverse

from apps.backlog.models import BacklogItem
from apps.projects.models import ProjectMembership
from apps.sprints.models import SprintItem
from tests.factories import add_member, make_item, make_project, make_sprint, make_user

Access = ProjectMembership.AccessLevel
Status = BacklogItem.Status


class BulkEditTests(TestCase):
    def setUp(self):
        self.project = make_project("BULK")
        self.lead = make_user()
        add_member(self.project, self.lead, access_level=Access.MANAGE)
        self.first = make_item(self.project, title="Eins")
        self.second = make_item(self.project, title="Zwei")
        self.url = reverse("backlog:bulk", args=["BULK"])
        self.client.force_login(self.lead)

    def post(self, action, value="", items=None):
        numbers = items or [self.first.number, self.second.number]
        return self.client.post(
            self.url, {"action": action, "value": value, "items": numbers}
        )

    def refreshed(self):
        self.first.refresh_from_db()
        self.second.refresh_from_db()

    def test_sets_priority_for_all_selected_items(self):
        response = self.post("priority", BacklogItem.Priority.HIGH)
        self.assertEqual(response.status_code, 302)
        self.refreshed()
        self.assertEqual(self.first.priority, BacklogItem.Priority.HIGH)
        self.assertEqual(self.second.priority, BacklogItem.Priority.HIGH)

    def test_assigns_and_unassigns_members(self):
        self.post("assignee", str(self.lead.pk))
        self.refreshed()
        self.assertEqual(self.second.assignee, self.lead)
        self.post("assignee", "none")
        self.refreshed()
        self.assertIsNone(self.first.assignee)

    def test_moves_items_into_sprint(self):
        sprint = make_sprint(self.project)
        self.post("sprint", str(sprint.number))
        self.assertEqual(
            SprintItem.objects.filter(sprint=sprint, outcome="open").count(), 2
        )

    def test_archives_items(self):
        self.post("archive")
        self.assertEqual(self.project.items.active().count(), 0)

    def test_workflow_violations_are_reported_and_others_still_change(self):
        self.project.use_review_column = True
        self.project.require_review = True
        self.project.save()
        self.second.status = Status.IN_REVIEW
        self.second.save()
        response = self.post("status", Status.DONE)
        self.refreshed()
        self.assertEqual(self.first.status, Status.TODO)
        self.assertEqual(self.second.status, Status.DONE)
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any(self.first.key in message for message in messages))

    def test_items_of_other_projects_are_ignored(self):
        foreign = make_item(make_project("FREM"), title="Fremd")
        self.client.post(
            self.url,
            {"action": "priority", "value": "high", "items": [foreign.number]},
        )
        foreign.refresh_from_db()
        self.assertNotEqual(foreign.priority, "high")

    def test_developer_may_only_change_status(self):
        developer = make_user()
        add_member(self.project, developer, access_level=Access.EDIT)
        self.client.force_login(developer)
        self.assertEqual(self.post("priority", "high").status_code, 403)
        self.post("status", Status.IN_PROGRESS)
        self.refreshed()
        self.assertEqual(self.first.status, Status.IN_PROGRESS)

    def test_readers_are_forbidden(self):
        reader = make_user()
        add_member(self.project, reader, access_level=Access.READ)
        self.client.force_login(reader)
        self.assertEqual(self.post("status", Status.DONE).status_code, 403)

    def test_unknown_action_is_rejected(self):
        self.assertEqual(self.post("delete").status_code, 400)

    def test_list_shows_bulk_toolbar_for_editors(self):
        response = self.client.get(reverse("backlog:list", args=["BULK"]))
        self.assertContains(response, 'name="items"')
        self.assertContains(response, reverse("backlog:bulk", args=["BULK"]))
