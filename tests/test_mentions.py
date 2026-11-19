from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.backlog.models import BacklogItem
from apps.backlog.services import add_comment, change_item_status, update_backlog_item
from apps.notifications.models import ItemWatch, Notification
from apps.notifications.services import extract_mentions, is_watching
from apps.projects.models import ProjectMembership
from apps.sprints.services import add_item_to_sprint, start_sprint
from tests.factories import add_member, make_item, make_project, make_sprint, make_user

Access = ProjectMembership.AccessLevel
Kind = Notification.Kind


class MentionAndWatchTests(TestCase):
    def setUp(self):
        self.project = make_project("NOTE")
        self.anna = make_user("anna", first_name="Anna", last_name="A.")
        self.bert = make_user("bert", first_name="Bert", last_name="B.")
        self.carl = make_user("carl", first_name="Carl", last_name="C.")
        self.outsider = make_user("otto")
        for user in (self.anna, self.bert, self.carl):
            add_member(self.project, user, access_level=Access.MANAGE)
        self.item = make_item(self.project, actor=self.anna, title="Login")

    def notifications(self, user, kind=None):
        queryset = Notification.objects.filter(recipient=user)
        return queryset.filter(kind=kind) if kind else queryset

    def test_extract_mentions_matches_members_only(self):
        text = "Hi @Bert und @otto, siehe @bert und @nobody"
        self.assertEqual(extract_mentions(text, self.project), [self.bert])

    def test_creator_assignee_and_commenter_watch_automatically(self):
        self.assertTrue(is_watching(self.item, self.anna))
        update_backlog_item(
            self.item, actor=self.anna, expected_version=None, assignee=self.bert
        )
        self.assertTrue(is_watching(self.item, self.bert))
        with self.captureOnCommitCallbacks(execute=True):
            add_comment(self.item, author=self.carl, body="Ich schaue mir das an.")
        self.assertTrue(is_watching(self.item, self.carl))

    def test_assignment_creates_in_app_notification(self):
        update_backlog_item(
            self.item, actor=self.anna, expected_version=None, assignee=self.bert
        )
        notification = self.notifications(self.bert, Kind.ASSIGNED).get()
        self.assertEqual(notification.item, self.item)
        self.assertEqual(notification.actor, self.anna)

    def test_mention_notifies_in_app_and_by_mail(self):
        with self.captureOnCommitCallbacks(execute=True):
            add_comment(self.item, author=self.anna, body="@carl kannst du helfen?")
        self.assertEqual(self.notifications(self.carl, Kind.MENTIONED).count(), 1)
        self.assertFalse(self.notifications(self.carl, Kind.COMMENTED).exists())
        self.assertFalse(self.notifications(self.anna).exists())
        mention_mails = [m for m in mail.outbox if "erwähnt" in m.subject]
        self.assertEqual([m.to for m in mention_mails], [[self.carl.email]])

    def test_comment_notifies_watchers_except_author(self):
        ItemWatch.objects.create(item=self.item, user=self.bert)
        with self.captureOnCommitCallbacks(execute=True):
            add_comment(self.item, author=self.carl, body="Erledigt.")
        self.assertEqual(self.notifications(self.anna, Kind.COMMENTED).count(), 1)
        self.assertEqual(self.notifications(self.bert, Kind.COMMENTED).count(), 1)
        self.assertFalse(self.notifications(self.carl).exists())

    def test_status_change_notifies_watchers_without_mail(self):
        ItemWatch.objects.create(item=self.item, user=self.bert)
        sprint = make_sprint(self.project)
        add_item_to_sprint(sprint, self.item, actor=self.anna)
        start_sprint(sprint, actor=self.anna)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            change_item_status(
                self.item, BacklogItem.Status.IN_PROGRESS, actor=self.anna
            )
        notification = self.notifications(self.bert, Kind.STATUS_CHANGED).get()
        self.assertIn("In Progress", notification.message)
        self.assertFalse(self.notifications(self.anna, Kind.STATUS_CHANGED).exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_former_members_are_not_notified(self):
        ItemWatch.objects.create(item=self.item, user=self.bert)
        ProjectMembership.objects.filter(user=self.bert).update(is_active=False)
        with self.captureOnCommitCallbacks(execute=True):
            add_comment(self.item, author=self.carl, body="@bert hallo")
        self.assertFalse(self.notifications(self.bert).exists())


class NotificationViewTests(TestCase):
    def setUp(self):
        self.project = make_project("NOTE")
        self.anna = make_user("anna", first_name="Anna", last_name="A.")
        self.bert = make_user("bert", first_name="Bert", last_name="B.")
        for user in (self.anna, self.bert):
            add_member(self.project, user, access_level=Access.MANAGE)
        self.item = make_item(self.project, actor=self.anna, title="Login")
        with self.captureOnCommitCallbacks(execute=True):
            add_comment(self.item, author=self.bert, body="@anna <b>bitte</b> prüfen")
        self.notification = Notification.objects.get(recipient=self.anna)
        self.client.force_login(self.anna)

    def test_bell_shows_unread_count(self):
        response = self.client.get(reverse("reporting:dashboard"))
        self.assertEqual(response.context["unread_notifications"], 1)
        self.assertContains(response, "ab-bell")
        count = self.client.get(reverse("notifications:unread_count"))
        self.assertEqual(count.json(), {"count": 1})

    def test_opening_marks_read_and_redirects_to_item(self):
        response = self.client.get(
            reverse("notifications:open", args=[self.notification.pk])
        )
        self.assertRedirects(
            response, reverse("backlog:detail", args=["NOTE", self.item.number])
        )
        self.notification.refresh_from_db()
        self.assertIsNotNone(self.notification.read_at)

    def test_other_users_notification_is_not_found(self):
        self.client.force_login(self.bert)
        response = self.client.get(
            reverse("notifications:open", args=[self.notification.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_mark_all_read(self):
        response = self.client.post(reverse("notifications:mark_all_read"))
        self.assertRedirects(response, reverse("notifications:list"))
        self.assertFalse(Notification.objects.filter(read_at__isnull=True).exists())

    def test_watch_toggle(self):
        url = reverse("backlog:watch", args=["NOTE", self.item.number])
        self.client.force_login(self.bert)
        self.client.post(url)
        self.assertFalse(is_watching(self.item, self.bert))
        self.client.post(url)
        self.assertTrue(is_watching(self.item, self.bert))

    def test_comment_highlights_mentions_and_escapes_html(self):
        response = self.client.get(
            reverse("backlog:detail", args=["NOTE", self.item.number])
        )
        self.assertContains(response, '<span class="mention">@anna</span>')
        self.assertContains(response, "&lt;b&gt;bitte&lt;/b&gt;")
        self.assertContains(response, "data-mention-users")
