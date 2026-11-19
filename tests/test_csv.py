import csv
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.backlog.models import BacklogItem
from apps.projects.models import ProjectMembership
from tests.factories import add_member, make_item, make_project, make_user

Access = ProjectMembership.AccessLevel


def csv_upload(text: str, name: str = "import.csv") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, text.encode("utf-8-sig"), "text/csv")


class CsvExportTests(TestCase):
    def setUp(self):
        self.project = make_project("CSV")
        self.reader = make_user("leser")
        add_member(self.project, self.reader, access_level=Access.READ)
        make_item(self.project, title="Login", item_type="bug", story_points=3)
        make_item(self.project, title="Export", item_type="task")
        self.url = reverse("backlog:export_csv", args=["CSV"])
        self.client.force_login(self.reader)

    def rows(self, response):
        text = response.content.decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(text), delimiter=";"))

    def test_readers_can_export_all_active_items(self):
        response = self.client.get(self.url)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment", response["Content-Disposition"])
        rows = self.rows(response)
        self.assertEqual([row["Titel"] for row in rows], ["Login", "Export"])
        self.assertEqual(rows[0]["Story Points"], "3")
        self.assertEqual(rows[0]["Typ"], "Bug")

    def test_export_respects_list_filters(self):
        rows = self.rows(self.client.get(self.url, {"type": "task"}))
        self.assertEqual([row["Titel"] for row in rows], ["Export"])

    def test_formula_injection_is_neutralised(self):
        make_item(self.project, title="=HYPERLINK(1)")
        rows = self.rows(self.client.get(self.url))
        self.assertEqual(rows[-1]["Titel"], "'=HYPERLINK(1)")


class CsvImportTests(TestCase):
    def setUp(self):
        self.project = make_project("IMP")
        self.lead = make_user("lead")
        self.dev = make_user("dev")
        add_member(self.project, self.lead, access_level=Access.MANAGE)
        add_member(self.project, self.dev)
        self.url = reverse("backlog:import_csv", args=["IMP"])
        self.client.force_login(self.lead)

    def upload(self, text):
        return self.client.post(self.url, {"file": csv_upload(text)})

    def test_imports_rows_with_labels_or_codes(self):
        response = self.upload(
            "Titel;Typ;Priorität;Story Points;Bearbeiter;Beschreibung\n"
            "Login bauen;User Story;Hoch;5;dev;Mit **SSO**\n"
            "Fehler fixen;bug;low;;;\n"
        )
        self.assertRedirects(response, reverse("backlog:list", args=["IMP"]))
        first, second = self.project.items.order_by("number")
        self.assertEqual(first.item_type, BacklogItem.ItemType.STORY)
        self.assertEqual(first.priority, BacklogItem.Priority.HIGH)
        self.assertEqual(first.story_points, 5)
        self.assertEqual(first.assignee, self.dev)
        self.assertEqual(first.description, "Mit **SSO**")
        self.assertEqual(second.item_type, BacklogItem.ItemType.BUG)
        self.assertIsNone(second.assignee)

    def test_comma_separated_files_are_accepted(self):
        self.upload("title,type\nKomma,task\n")
        self.assertEqual(self.project.items.get().title, "Komma")

    def test_invalid_rows_import_nothing_and_are_reported(self):
        response = self.upload(
            "Titel;Typ;Story Points;Bearbeiter\n"
            "Gut;task;3;\n"
            ";task;;\n"
            "Schlecht;Rakete;500;fremd\n"
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.project.items.exists())
        self.assertContains(response, "Zeile 3")
        self.assertContains(response, "Zeile 4")
        self.assertContains(response, "Rakete")
        self.assertContains(response, "fremd")

    def test_missing_title_column_is_rejected(self):
        response = self.upload("Typ\nbug\n")
        self.assertContains(response, "Spalte „Titel“ fehlt")
        self.assertFalse(self.project.items.exists())

    def test_developers_cannot_import(self):
        self.client.force_login(self.dev)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_exported_file_can_be_imported_again(self):
        make_item(self.project, title="Rundreise", item_type="bug", story_points=2)
        exported = self.client.get(reverse("backlog:export_csv", args=["IMP"]))
        self.upload(exported.content.decode("utf-8-sig"))
        copies = self.project.items.filter(title="Rundreise")
        self.assertEqual(copies.count(), 2)
        self.assertEqual(copies.last().story_points, 2)
