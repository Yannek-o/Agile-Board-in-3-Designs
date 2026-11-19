from django.core import mail
from django.core.mail.backends.base import BaseEmailBackend
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.backlog.models import BacklogItem
from apps.backlog.services import add_comment, update_backlog_item
from apps.projects.models import ProjectMembership
from apps.sprints.services import add_item_to_sprint, complete_sprint, start_sprint
from tests.factories import (
    add_member,
    make_item,
    make_project,
    make_sprint,
    make_user,
)


class FailingEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        raise ConnectionRefusedError("SMTP nicht erreichbar")


@override_settings(SITE_URL="https://agile.example.com")
class NotificationTests(TestCase):
    def setUp(self):
        self.project = make_project("HELP")
        self.lead = make_user("lead", email="lead@example.com")
        self.dev = make_user("dev", email="dev@example.com")
        self.quiet = make_user(
            "quiet", email="quiet@example.com", email_notifications=False
        )
        add_member(
            self.project, self.lead,
            access_level=ProjectMembership.AccessLevel.MANAGE,
        )
        add_member(self.project, self.dev)
        add_member(self.project, self.quiet)
        self.item = make_item(self.project, actor=self.lead, title="Ticketstatus")

    def assign(self, user, actor):
        with self.captureOnCommitCallbacks(execute=True):
            update_backlog_item(
                self.item, actor=actor, expected_version=self.item.version,
                assignee=user,
            )

    def test_assignment_notifies_new_assignee_with_link(self):
        self.assign(self.dev, actor=self.lead)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["dev@example.com"])
        self.assertIn("HELP-1", message.subject)
        self.assertIn(
            "https://agile.example.com/projects/HELP/backlog/items/1/", message.body
        )

    def test_self_assignment_and_opt_out_send_nothing(self):
        self.assign(self.dev, actor=self.dev)
        self.assign(self.quiet, actor=self.lead)
        self.assertEqual(len(mail.outbox), 0)

    def test_comment_notifies_assignee_and_creator_but_not_author(self):
        self.assign(self.dev, actor=self.lead)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            add_comment(self.item, author=self.dev, body="Erledigt?")
        recipients = sorted(address for m in mail.outbox for address in m.to)
        self.assertEqual(recipients, ["lead@example.com"])

    def test_sprint_start_and_completion_notify_members(self):
        sprint = make_sprint(self.project)
        add_item_to_sprint(sprint, self.item, actor=self.lead)
        with self.captureOnCommitCallbacks(execute=True):
            start_sprint(sprint, actor=self.lead)
        self.assertEqual(
            sorted(address for m in mail.outbox for address in m.to),
            ["dev@example.com"],
        )
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            complete_sprint(sprint, actor=self.lead)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("abgeschlossen", mail.outbox[0].subject)

    @override_settings(
        EMAIL_BACKEND="tests.test_notifications.FailingEmailBackend"
    )
    def test_mail_failure_does_not_break_the_change(self):
        self.assign(self.dev, actor=self.lead)
        self.item.refresh_from_db()
        self.assertEqual(self.item.assignee, self.dev)

    def test_user_can_disable_notifications_in_profile(self):
        self.client.force_login(self.dev)
        self.client.post(
            reverse("accounts:profile"),
            {
                "first_name": "D",
                "last_name": "V",
                "email": "dev@example.com",
                "job_title": "",
            },
        )
        self.dev.refresh_from_db()
        self.assertFalse(self.dev.email_notifications)

    def test_board_item_status_change_does_not_send_mail(self):
        with self.captureOnCommitCallbacks(execute=True):
            update_backlog_item(
                self.item, actor=self.lead, expected_version=self.item.version,
                status=BacklogItem.Status.IN_PROGRESS,
            )
        self.assertEqual(len(mail.outbox), 0)
