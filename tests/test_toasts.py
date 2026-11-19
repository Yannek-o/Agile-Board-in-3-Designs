from django.contrib.messages import constants
from django.contrib.messages.storage.base import Message
from django.test import TestCase
from django.urls import reverse

from apps.core.templatetags.agile import message_kind, message_undo_url
from apps.core.toasts import undo_tag
from apps.projects.models import ProjectMembership
from tests.factories import add_member, make_item, make_project, make_user

Access = ProjectMembership.AccessLevel


class UndoToastTests(TestCase):
    def setUp(self):
        self.user = make_user("ben")
        self.project = make_project("HELP")
        add_member(self.project, self.user, access_level=Access.MANAGE)
        self.item = make_item(self.project, title="Ticket")
        self.client.force_login(self.user)

    def item_url(self, name: str) -> str:
        return reverse(f"backlog:{name}", args=[self.project.key, self.item.number])

    def test_archiving_offers_undo_that_restores_the_item(self):
        response = self.client.post(self.item_url("archive"), follow=True)
        self.assertContains(response, 'class="ab-toast toast-success"')
        self.assertContains(
            response, f'data-undo-url="{self.item_url("restore")}"'
        )
        self.client.post(self.item_url("restore"))
        self.item.refresh_from_db()
        self.assertIsNone(self.item.archived_at)

    def test_plain_messages_are_toasts_without_undo(self):
        response = self.client.post(self.item_url("restore"), follow=True)
        self.assertContains(response, 'class="ab-toast toast-success"')
        self.assertNotContains(response, "data-undo-url")


class MessageFilterTests(TestCase):
    def test_kind_follows_the_message_level(self):
        self.assertEqual(message_kind(Message(constants.ERROR, "x")), "danger")
        self.assertEqual(message_kind(Message(constants.SUCCESS, "x")), "success")
        self.assertEqual(message_kind(Message(constants.DEBUG, "x")), "info")

    def test_only_local_undo_urls_are_accepted(self):
        local = Message(constants.SUCCESS, "x", extra_tags=undo_tag("/a/restore/"))
        foreign = Message(
            constants.SUCCESS, "x", extra_tags=undo_tag("//evil.example/")
        )
        self.assertEqual(message_undo_url(local), "/a/restore/")
        self.assertEqual(message_undo_url(foreign), "")
        self.assertEqual(message_undo_url(Message(constants.INFO, "x")), "")
