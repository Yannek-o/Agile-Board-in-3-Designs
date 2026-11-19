import json

from django.test import Client, TestCase
from django.urls import reverse

from apps.api.models import ApiToken
from apps.backlog.models import BacklogItem
from apps.projects.models import ProjectMembership
from tests.factories import add_member, make_item, make_project, make_sprint, make_user

Access = ProjectMembership.AccessLevel


class ApiTestCase(TestCase):
    def setUp(self):
        self.project = make_project("API")
        self.lead = make_user("lead")
        self.dev = make_user("dev")
        add_member(self.project, self.lead, access_level=Access.MANAGE)
        add_member(self.project, self.dev)
        self.item = make_item(self.project, title="Login", story_points=3)
        make_project("SECRET")
        self.token, self.raw_token = ApiToken.issue(self.lead, name="CI")

    def api(self, method, url, data=None, token=None, **extra):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {token or self.raw_token}"}
        body = json.dumps(data) if data is not None else None
        return getattr(self.client, method)(
            url, body, content_type="application/json", **headers, **extra
        )


class ApiTokenTests(ApiTestCase):
    def test_only_hash_is_stored(self):
        self.assertNotIn(self.raw_token, self.token.key_hash)
        self.assertTrue(self.raw_token.startswith(self.token.prefix))

    def test_missing_or_wrong_token_is_401(self):
        url = reverse("api:projects")
        self.assertEqual(Client().get(url).status_code, 401)
        self.assertEqual(self.api("get", url, token="ab_wrong").status_code, 401)

    def test_revoked_token_is_rejected(self):
        self.token.delete()
        self.assertEqual(self.api("get", reverse("api:projects")).status_code, 401)

    def test_inactive_users_cannot_use_tokens(self):
        self.lead.is_active = False
        self.lead.save()
        self.assertEqual(self.api("get", reverse("api:projects")).status_code, 401)

    def test_profile_page_creates_and_revokes_tokens(self):
        self.client.force_login(self.dev)
        url = reverse("api:tokens")
        response = self.client.post(url, {"name": "Skript"})
        token = ApiToken.objects.get(user=self.dev)
        self.assertContains(response, token.prefix)
        self.assertContains(response, "nur jetzt sichtbar")
        self.client.post(reverse("api:token_delete", args=[token.pk]))
        self.assertFalse(ApiToken.objects.filter(user=self.dev).exists())

    def test_session_auth_works_but_needs_csrf_for_writes(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.lead)
        self.assertEqual(client.get(reverse("api:projects")).status_code, 200)
        response = client.post(
            reverse("api:items", args=["API"]),
            json.dumps({"title": "Ohne CSRF"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)


class ApiReadTests(ApiTestCase):
    def test_projects_lists_only_visible_projects(self):
        data = self.api("get", reverse("api:projects")).json()
        self.assertEqual([p["key"] for p in data["results"]], ["API"])

    def test_items_list_supports_backlog_filters(self):
        make_item(self.project, title="Bug", item_type="bug")
        data = self.api(
            "get", reverse("api:items", args=["API"]) + "?type=bug"
        ).json()
        self.assertEqual([i["title"] for i in data["results"]], ["Bug"])
        self.assertEqual(data["count"], 1)

    def test_item_detail(self):
        data = self.api(
            "get", reverse("api:item", args=["API", self.item.number])
        ).json()
        self.assertEqual(data["key"], self.item.key)
        self.assertEqual(data["story_points"], 3)
        self.assertEqual(data["status"], "todo")

    def test_foreign_projects_are_404(self):
        response = self.api("get", reverse("api:items", args=["SECRET"]))
        self.assertEqual(response.status_code, 404)

    def test_sprints(self):
        make_sprint(self.project, name="Sprint A")
        data = self.api("get", reverse("api:sprints", args=["API"])).json()
        self.assertEqual(data["results"][0]["status"], "planned")


class ApiWriteTests(ApiTestCase):
    def test_create_item(self):
        response = self.api(
            "post",
            reverse("api:items", args=["API"]),
            {"title": "Neu", "item_type": "bug", "assignee": "dev"},
        )
        self.assertEqual(response.status_code, 201)
        item = self.project.items.get(title="Neu")
        self.assertEqual(item.assignee, self.dev)
        self.assertEqual(response.json()["key"], item.key)

    def test_create_validates_input(self):
        response = self.api(
            "post", reverse("api:items", args=["API"]), {"item_type": "rocket"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("title", response.json()["errors"])

    def test_patch_status_and_fields(self):
        url = reverse("api:item", args=["API", self.item.number])
        response = self.api(
            "patch", url, {"status": "in_progress", "story_points": 5}
        )
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, BacklogItem.Status.IN_PROGRESS)
        self.assertEqual(self.item.story_points, 5)

    def test_patch_detects_version_conflicts(self):
        url = reverse("api:item", args=["API", self.item.number])
        response = self.api("patch", url, {"status": "done", "version": 0})
        self.assertEqual(response.status_code, 409)

    def test_workflow_rules_apply(self):
        self.project.use_review_column = True
        self.project.require_review = True
        self.project.save()
        url = reverse("api:item", args=["API", self.item.number])
        response = self.api("patch", url, {"status": "done"})
        self.assertEqual(response.status_code, 400)

    def test_developers_may_only_change_status(self):
        _, dev_token = ApiToken.issue(self.dev, name="dev")
        url = reverse("api:item", args=["API", self.item.number])
        denied = self.api("patch", url, {"story_points": 8}, token=dev_token)
        self.assertEqual(denied.status_code, 403)
        allowed = self.api("patch", url, {"status": "in_progress"}, token=dev_token)
        self.assertEqual(allowed.status_code, 200)
        created = self.api(
            "post", reverse("api:items", args=["API"]), {"title": "X"},
            token=dev_token,
        )
        self.assertEqual(created.status_code, 403)
