from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.activity.models import ActivityEvent
from apps.backlog.forms import BacklogItemForm
from apps.backlog.models import AcceptanceCriterion, Attachment, BacklogItem
from apps.backlog.services import (
    ConcurrentModificationError,
    add_attachment,
    archive_item,
    change_item_status,
    move_item_in_backlog,
    update_backlog_item,
)
from apps.projects.models import Label, ProjectMembership
from tests.factories import add_member, make_item, make_project, make_user

Access = ProjectMembership.AccessLevel
Status = BacklogItem.Status


class BacklogServiceTests(TestCase):
    def setUp(self):
        self.project = make_project("HELP")
        self.developer = make_user("dev")
        add_member(self.project, self.developer)

    def test_item_numbers_are_sequential_per_project(self):
        first = make_item(self.project)
        second = make_item(self.project)
        other = make_item(make_project("SHOP"))
        self.assertEqual(first.key, "HELP-1")
        self.assertEqual(second.key, "HELP-2")
        self.assertEqual(other.key, "SHOP-1")

    def test_new_items_are_appended_to_backlog_order(self):
        first = make_item(self.project, priority=BacklogItem.Priority.LOW)
        second = make_item(self.project, priority=BacklogItem.Priority.CRITICAL)
        ordered = list(BacklogItem.objects.filter(project=self.project))
        self.assertEqual(ordered, [first, second])

    def test_backlog_order_is_independent_from_priority(self):
        first = make_item(self.project)
        second = make_item(self.project)
        third = make_item(self.project)
        move_item_in_backlog(third, 0, actor=self.developer)
        ordered = list(BacklogItem.objects.filter(project=self.project))
        self.assertEqual(ordered, [third, first, second])
        self.assertEqual(third.priority, BacklogItem.Priority.MEDIUM)

    def test_creation_with_criteria_and_activity(self):
        item = make_item(
            self.project,
            actor=self.developer,
            acceptance_criteria=["Status wird gespeichert", "Verlauf sichtbar"],
        )
        self.assertEqual(item.acceptance_criteria.count(), 2)
        self.assertTrue(
            ActivityEvent.objects.filter(
                item=item, action=ActivityEvent.Action.CREATED
            ).exists()
        )

    def test_assignee_must_be_active_project_member(self):
        outsider = make_user()
        with self.assertRaises(ValidationError):
            make_item(self.project, assignee=outsider)

    def test_story_points_must_not_be_negative(self):
        item = make_item(self.project)
        item.story_points = -1
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_stale_update_is_rejected(self):
        item = make_item(self.project)
        update_backlog_item(
            item, actor=self.developer, expected_version=item.version,
            title="Neu",
        )
        stale = BacklogItem.objects.get(pk=item.pk)
        stale.version = 1
        with self.assertRaises(ConcurrentModificationError):
            update_backlog_item(
                stale, actor=self.developer, expected_version=1, title="Alt"
            )
        item.refresh_from_db()
        self.assertEqual(item.title, "Neu")

    def test_update_records_changed_fields(self):
        item = make_item(self.project)
        update_backlog_item(
            item, actor=self.developer, expected_version=item.version,
            priority=BacklogItem.Priority.HIGH,
        )
        event = ActivityEvent.objects.get(
            item=item, action=ActivityEvent.Action.UPDATED
        )
        self.assertEqual(event.field, "priority")
        self.assertEqual(event.new_value, "Hoch")

    def test_status_change_sets_completion_and_logs_history(self):
        item = make_item(self.project)
        change_item_status(item, Status.DONE, actor=self.developer)
        item.refresh_from_db()
        self.assertEqual(item.status, Status.DONE)
        self.assertIsNotNone(item.completed_at)
        event = ActivityEvent.objects.get(
            item=item, action=ActivityEvent.Action.STATUS_CHANGED
        )
        self.assertEqual(event.old_value, "To Do")
        self.assertEqual(event.new_value, "Done")
        change_item_status(item, Status.IN_PROGRESS, actor=self.developer)
        item.refresh_from_db()
        self.assertIsNone(item.completed_at)

    def test_archived_items_are_hidden_from_active_backlog(self):
        item = make_item(self.project)
        archive_item(item, actor=self.developer)
        self.assertNotIn(item, BacklogItem.objects.active())

    def test_attachment_with_forbidden_extension_is_rejected(self):
        item = make_item(self.project)
        upload = SimpleUploadedFile("virus.exe", b"MZ", "application/octet-stream")
        with self.assertRaises(ValidationError):
            add_attachment(item, uploaded_by=self.developer, uploaded_file=upload)

    def test_attachment_is_stored_with_metadata(self):
        item = make_item(self.project)
        upload = SimpleUploadedFile("notiz.txt", b"Hallo", "text/plain")
        attachment = add_attachment(
            item, uploaded_by=self.developer, uploaded_file=upload
        )
        self.assertEqual(attachment.original_name, "notiz.txt")
        self.assertEqual(attachment.size, 5)


class BacklogFormTests(TestCase):
    def setUp(self):
        self.project = make_project("HELP")
        self.member = make_user()
        add_member(self.project, self.member)

    def form(self, **overrides):
        data = {
            "item_type": BacklogItem.ItemType.STORY,
            "title": "Ticketstatus ändern",
            "description": "",
            "priority": BacklogItem.Priority.HIGH,
            "story_points": 5,
            "status": Status.TODO,
            "acceptance_criteria_text": "Kriterium A\nKriterium B",
        }
        data.update(overrides)
        return BacklogItemForm(data=data, project=self.project)

    def test_valid_form(self):
        form = self.form(assignee=self.member.pk)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data["acceptance_criteria_text"],
            ["Kriterium A", "Kriterium B"],
        )

    def test_assignee_outside_project_is_invalid(self):
        self.assertFalse(self.form(assignee=make_user().pk).is_valid())

    def test_label_of_other_project_is_invalid(self):
        foreign_label = Label.objects.create(project=make_project(), name="X")
        self.assertFalse(self.form(labels=[foreign_label.pk]).is_valid())

    def test_empty_title_and_huge_points_are_invalid(self):
        self.assertFalse(self.form(title="  ").is_valid())
        self.assertFalse(self.form(story_points=1000).is_valid())


class BacklogViewTests(TestCase):
    def setUp(self):
        self.project = make_project("HELP")
        self.planner = make_user("planner")
        self.editor = make_user("editor")
        self.reader = make_user("reader")
        add_member(self.project, self.planner, access_level=Access.MANAGE)
        add_member(self.project, self.editor, access_level=Access.EDIT)
        add_member(self.project, self.reader, access_level=Access.READ)
        self.item = make_item(self.project, title="Ticketstatus ändern")
        self.list_url = reverse("backlog:list", args=["HELP"])

    def item_url(self, name, item=None, *extra):
        item = item or self.item
        return reverse(
            f"backlog:{name}", args=[item.project.key, item.number, *extra]
        )

    def test_backlog_list_supports_search_by_key_and_title(self):
        make_item(self.project, title="Suchfunktion optimieren")
        self.client.force_login(self.reader)
        response = self.client.get(self.list_url, {"q": "HELP-1"})
        self.assertContains(response, "Ticketstatus ändern")
        self.assertNotContains(response, "Suchfunktion optimieren")
        response = self.client.get(self.list_url, {"q": "such"})
        self.assertContains(response, "Suchfunktion optimieren")

    def test_backlog_list_filters_by_type_and_priority(self):
        make_item(
            self.project, title="Fehler bei Anhängen",
            item_type=BacklogItem.ItemType.BUG,
        )
        self.client.force_login(self.reader)
        response = self.client.get(self.list_url, {"type": "bug"})
        self.assertContains(response, "Fehler bei Anhängen")
        self.assertNotContains(response, "Ticketstatus ändern")

    def test_backlog_list_escapes_html(self):
        make_item(self.project, title="<script>alert(1)</script>")
        self.client.force_login(self.reader)
        response = self.client.get(self.list_url)
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")

    def test_planner_creates_item(self):
        self.client.force_login(self.planner)
        response = self.client.post(
            reverse("backlog:create", args=["HELP"]),
            {
                "item_type": BacklogItem.ItemType.BUG,
                "title": "Dateianhänge beheben",
                "priority": BacklogItem.Priority.HIGH,
                "status": Status.TODO,
                "story_points": 2,
                "acceptance_criteria_text": "Upload funktioniert",
            },
        )
        item = BacklogItem.objects.get(title="Dateianhänge beheben")
        self.assertRedirects(response, self.item_url("detail", item))
        self.assertEqual(item.created_by, self.planner)
        self.assertEqual(item.acceptance_criteria.count(), 1)

    def test_editor_without_approval_and_reader_cannot_create(self):
        for user in (self.editor, self.reader):
            self.client.force_login(user)
            response = self.client.get(reverse("backlog:create", args=["HELP"]))
            self.assertEqual(response.status_code, 403)

    def test_edit_with_stale_version_shows_conflict(self):
        self.client.force_login(self.planner)
        data = {
            "item_type": BacklogItem.ItemType.STORY,
            "title": "Neuer Titel",
            "priority": BacklogItem.Priority.HIGH,
            "status": Status.TODO,
            "version": self.item.version,
        }
        self.client.post(self.item_url("edit"), data)
        response = self.client.post(self.item_url("edit"), data)
        self.assertEqual(response.status_code, 409)

    def test_editor_without_approval_edits_only_working_fields(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            self.item_url("edit"),
            {
                "description": "Neue Details",
                "assignee": self.editor.pk,
                "status": Status.IN_PROGRESS,
                "priority": BacklogItem.Priority.CRITICAL,
                "title": "Manipuliert",
                "version": self.item.version,
            },
        )
        self.assertRedirects(response, self.item_url("detail"))
        self.item.refresh_from_db()
        self.assertEqual(self.item.description, "Neue Details")
        self.assertEqual(self.item.assignee, self.editor)
        self.assertEqual(self.item.priority, BacklogItem.Priority.MEDIUM)
        self.assertEqual(self.item.title, "Ticketstatus ändern")

    def test_reader_cannot_edit(self):
        self.client.force_login(self.reader)
        self.assertEqual(self.client.get(self.item_url("edit")).status_code, 403)

    def test_editor_and_reader_comment_rights(self):
        self.client.force_login(self.editor)
        self.client.post(self.item_url("comment"), {"body": "Sieht gut aus"})
        self.assertEqual(self.item.comments.count(), 1)
        self.client.force_login(self.reader)
        response = self.client.post(self.item_url("comment"), {"body": "Hi"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.item.comments.count(), 1)

    def test_item_cannot_be_read_through_foreign_project(self):
        other = make_project("OTHER")
        add_member(other, self.reader)
        self.client.force_login(self.reader)
        response = self.client.get(
            reverse("backlog:detail", args=["OTHER", self.item.number])
        )
        self.assertEqual(response.status_code, 404)

    def test_outsider_cannot_read_item(self):
        self.client.force_login(make_user())
        self.assertEqual(self.client.get(self.item_url("detail")).status_code, 404)

    def test_reorder_endpoint_changes_rank(self):
        second = make_item(self.project)
        self.client.force_login(self.planner)
        response = self.client.post(
            reverse("backlog:reorder", args=["HELP"]),
            {"item": second.number, "position": 0},
        )
        self.assertEqual(response.status_code, 302)
        ordered = list(BacklogItem.objects.filter(project=self.project))
        self.assertEqual(ordered[0], second)

    def test_reader_cannot_reorder(self):
        self.client.force_login(self.reader)
        response = self.client.post(
            reverse("backlog:reorder", args=["HELP"]),
            {"item": self.item.number, "position": 0},
        )
        self.assertEqual(response.status_code, 403)

    def test_acceptance_criterion_toggle(self):
        criterion = AcceptanceCriterion.objects.create(
            item=self.item, text="Status gespeichert", position=1
        )
        self.client.force_login(self.editor)
        self.client.post(self.item_url("criterion_toggle", None, criterion.pk))
        criterion.refresh_from_db()
        self.assertTrue(criterion.is_met)

    def test_attachment_upload_and_protected_download(self):
        self.client.force_login(self.editor)
        upload = SimpleUploadedFile("log.txt", b"Fehlerprotokoll", "text/plain")
        self.client.post(self.item_url("attachment_upload"), {"file": upload})
        attachment = Attachment.objects.get(item=self.item)
        download_url = self.item_url("attachment_download", None, attachment.pk)
        response = self.client.get(download_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.client.force_login(make_user())
        self.assertEqual(self.client.get(download_url).status_code, 404)

    def test_archive_hides_item(self):
        self.client.force_login(self.planner)
        self.client.post(self.item_url("archive"))
        self.item.refresh_from_db()
        self.assertIsNotNone(self.item.archived_at)
        response = self.client.get(self.list_url)
        self.assertNotContains(response, "Ticketstatus ändern")
