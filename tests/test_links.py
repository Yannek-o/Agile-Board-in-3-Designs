from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.activity.models import ActivityEvent
from apps.backlog.models import BacklogItem, ItemLink
from apps.backlog.services import add_item_link, change_item_status, remove_item_link
from apps.projects.models import ProjectMembership
from apps.sprints.services import add_item_to_sprint, start_sprint
from tests.factories import add_member, make_item, make_project, make_sprint, make_user

Access = ProjectMembership.AccessLevel
LinkType = ItemLink.LinkType


class ItemLinkServiceTests(TestCase):
    def setUp(self):
        self.project = make_project("LINK")
        self.user = make_user()
        add_member(self.project, self.user, access_level=Access.MANAGE)
        self.first = make_item(self.project, title="API")
        self.second = make_item(self.project, title="Frontend")

    def test_link_is_shown_from_both_sides(self):
        add_item_link(self.first, self.second, LinkType.BLOCKS, actor=self.user)
        outgoing = self.first.link_overview()
        incoming = self.second.link_overview()
        self.assertEqual(outgoing[0]["label"], "blockiert")
        self.assertEqual(outgoing[0]["item"], self.second)
        self.assertEqual(incoming[0]["label"], "wird blockiert von")
        self.assertEqual(incoming[0]["item"], self.first)

    def test_relates_and_duplicates_labels(self):
        add_item_link(self.first, self.second, LinkType.RELATES, actor=self.user)
        third = make_item(self.project)
        add_item_link(third, self.first, LinkType.DUPLICATES, actor=self.user)
        labels = {entry["label"] for entry in self.first.link_overview()}
        self.assertEqual(labels, {"gehört zu", "hat Duplikat"})

    def test_cannot_link_item_to_itself(self):
        with self.assertRaises(ValidationError):
            add_item_link(self.first, self.first, LinkType.RELATES, actor=self.user)

    def test_cannot_link_across_projects(self):
        foreign = make_item(make_project("OTHR"))
        with self.assertRaises(ValidationError):
            add_item_link(self.first, foreign, LinkType.RELATES, actor=self.user)

    def test_duplicate_link_is_rejected_in_both_directions(self):
        add_item_link(self.first, self.second, LinkType.RELATES, actor=self.user)
        with self.assertRaises(ValidationError):
            add_item_link(self.second, self.first, LinkType.RELATES, actor=self.user)

    def test_link_changes_are_recorded(self):
        link = add_item_link(self.first, self.second, LinkType.BLOCKS, actor=self.user)
        remove_item_link(link, actor=self.user)
        events = ActivityEvent.objects.filter(item=self.first, field="links")
        self.assertEqual(events.count(), 2)
        self.assertFalse(ItemLink.objects.exists())

    def test_open_blockers_ignore_done_items(self):
        add_item_link(self.first, self.second, LinkType.BLOCKS, actor=self.user)
        self.assertEqual([b.pk for b in self.second.open_blockers()], [self.first.pk])
        sprint = make_sprint(self.project)
        add_item_to_sprint(sprint, self.first, actor=self.user)
        start_sprint(sprint, actor=self.user)
        change_item_status(self.first, BacklogItem.Status.DONE, actor=self.user)
        self.assertEqual(list(self.second.open_blockers()), [])


class ItemLinkViewTests(TestCase):
    def setUp(self):
        self.project = make_project("LINK")
        self.editor = make_user()
        self.reader = make_user()
        add_member(self.project, self.editor, access_level=Access.EDIT)
        add_member(self.project, self.reader, access_level=Access.READ)
        self.first = make_item(self.project, title="API")
        self.second = make_item(self.project, title="Frontend")
        self.url = reverse("backlog:link_add", args=["LINK", self.first.number])

    def test_editor_adds_link_by_key(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            self.url, {"link_type": LinkType.BLOCKS, "target": self.second.key}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            ItemLink.objects.filter(source=self.first, target=self.second).exists()
        )
        page = self.client.get(
            reverse("backlog:detail", args=["LINK", self.second.number])
        )
        self.assertContains(page, "wird blockiert von")
        self.assertContains(page, self.first.key)

    def test_unknown_target_shows_error(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            self.url, {"link_type": LinkType.RELATES, "target": "LINK-999"}, follow=True
        )
        self.assertContains(response, "nicht gefunden")
        self.assertFalse(ItemLink.objects.exists())

    def test_reader_cannot_add_links(self):
        self.client.force_login(self.reader)
        response = self.client.post(
            self.url, {"link_type": LinkType.RELATES, "target": self.second.key}
        )
        self.assertEqual(response.status_code, 403)

    def test_editor_removes_link(self):
        link = add_item_link(self.first, self.second, LinkType.RELATES, actor=None)
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse("backlog:link_delete", args=["LINK", self.second.number, link.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ItemLink.objects.exists())

    def test_board_card_shows_open_blocker(self):
        add_item_link(self.first, self.second, LinkType.BLOCKS, actor=None)
        sprint = make_sprint(self.project)
        add_item_to_sprint(sprint, self.second, actor=self.editor)
        start_sprint(sprint, actor=self.editor)
        self.client.force_login(self.editor)
        response = self.client.get(reverse("board:board", args=["LINK"]))
        self.assertContains(response, "Blockiert durch 1")
