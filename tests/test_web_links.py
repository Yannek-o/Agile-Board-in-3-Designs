from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.backlog.models import BacklogItem
from apps.backlog.services import add_web_link
from apps.projects.models import ProjectMembership
from tests.factories import add_member, make_item, make_project, make_user

Access = ProjectMembership.AccessLevel


class WebLinkServiceTests(TestCase):
    def setUp(self):
        self.project = make_project("WEB")
        self.user = make_user()
        add_member(self.project, self.user, access_level=Access.MANAGE)

    def test_item_is_created_with_attachments_and_web_links(self):
        item = make_item(
            self.project,
            actor=self.user,
            uploads=[
                SimpleUploadedFile("screenshot.png", b"\x89PNG", "image/png"),
                SimpleUploadedFile("konzept.pdf", b"%PDF-1.7", "application/pdf"),
            ],
            web_links=["https://example.com/spec"],
        )
        self.assertCountEqual(
            item.attachments.values_list("original_name", flat=True),
            ["screenshot.png", "konzept.pdf"],
        )
        self.assertEqual(
            list(item.web_links.values_list("url", flat=True)),
            ["https://example.com/spec"],
        )

    def test_invalid_upload_prevents_item_creation(self):
        upload = SimpleUploadedFile("virus.exe", b"MZ", "application/octet-stream")
        with self.assertRaises(ValidationError) as context:
            make_item(self.project, title="Mit Virus", uploads=[upload])
        self.assertIn("attachments", context.exception.error_dict)
        self.assertFalse(BacklogItem.objects.filter(title="Mit Virus").exists())

    def test_web_links_must_use_http_or_https(self):
        item = make_item(self.project)
        for url in ("javascript:alert(1)", "ftp://example.com/datei", "kein link"):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                add_web_link(item, actor=self.user, url=url)
        self.assertFalse(item.web_links.exists())

    def test_image_attachments_are_recognised(self):
        item = make_item(
            self.project,
            uploads=[SimpleUploadedFile("bild.png", b"\x89PNG", "image/png")],
        )
        self.assertTrue(item.attachments.get().is_image)


class WebLinkViewTests(TestCase):
    def setUp(self):
        self.project = make_project("WEB")
        self.planner = make_user()
        self.editor = make_user()
        self.reader = make_user()
        add_member(self.project, self.planner, access_level=Access.MANAGE)
        add_member(self.project, self.editor, access_level=Access.EDIT)
        add_member(self.project, self.reader, access_level=Access.READ)
        self.item = make_item(self.project)

    def url(self, name: str, *extra) -> str:
        return reverse(f"backlog:{name}", args=["WEB", self.item.number, *extra])

    def test_editor_adds_and_removes_web_link_reader_cannot(self):
        self.client.force_login(self.reader)
        response = self.client.post(
            self.url("web_link_add"), {"url": "https://example.com/doku"}
        )
        self.assertEqual(response.status_code, 403)
        self.client.force_login(self.editor)
        self.client.post(self.url("web_link_add"), {"url": "https://example.com/doku"})
        link = self.item.web_links.get()
        response = self.client.get(self.url("detail"))
        self.assertContains(
            response,
            'href="https://example.com/doku" target="_blank" rel="noopener noreferrer"',
        )
        self.client.post(self.url("web_link_delete", link.pk))
        self.assertFalse(self.item.web_links.exists())

    def test_planner_creates_item_with_attachments_and_links(self):
        self.client.force_login(self.planner)
        response = self.client.post(
            reverse("backlog:create", args=["WEB"]),
            {
                "item_type": BacklogItem.ItemType.BUG,
                "title": "Fehlerbild prüfen",
                "priority": BacklogItem.Priority.HIGH,
                "status": BacklogItem.Status.TODO,
                "attachments": [
                    SimpleUploadedFile("fehler.png", b"\x89PNG", "image/png"),
                    SimpleUploadedFile("folien.pdf", b"%PDF", "application/pdf"),
                ],
                "web_links": ["https://example.com/ticket", ""],
            },
        )
        item = BacklogItem.objects.get(title="Fehlerbild prüfen")
        self.assertRedirects(
            response, reverse("backlog:detail", args=["WEB", item.number])
        )
        self.assertEqual(item.attachments.count(), 2)
        self.assertEqual(item.web_links.get().url, "https://example.com/ticket")

    def test_create_form_shows_upload_errors_without_creating_item(self):
        self.client.force_login(self.planner)
        response = self.client.post(
            reverse("backlog:create", args=["WEB"]),
            {
                "item_type": BacklogItem.ItemType.BUG,
                "title": "Ungültige Anlage",
                "priority": BacklogItem.Priority.HIGH,
                "status": BacklogItem.Status.TODO,
                "attachments": [SimpleUploadedFile("tool.exe", b"MZ")],
                "web_links": ["javascript:alert(1)"],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dateityp nicht erlaubt")
        self.assertContains(response, "http:// oder https://")
        self.assertFalse(BacklogItem.objects.filter(title="Ungültige Anlage").exists())

    def test_edit_form_has_no_upload_fields(self):
        self.client.force_login(self.planner)
        response = self.client.get(self.url("edit"))
        self.assertNotIn("attachments", response.context["form"].fields)
        self.assertNotIn("web_links", response.context["form"].fields)
