from django.test import TestCase
from django.urls import reverse

from apps.backlog.models import SavedFilter
from apps.backlog.services import archive_item
from apps.projects.models import ProjectMembership
from tests.factories import add_member, make_item, make_project, make_user

Access = ProjectMembership.AccessLevel


class GlobalSearchTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.project = make_project("SRCH")
        add_member(self.project, self.user)
        self.match = make_item(self.project, title="Login reparieren")
        self.other = make_item(
            self.project, title="Export", description="Login-Hinweis"
        )
        foreign = make_project("HIDE")
        make_item(foreign, title="Login geheim")
        self.url = reverse("core:search")
        self.client.force_login(self.user)

    def titles(self, response):
        return [item.title for item in response.context["results"]]

    def test_text_search_covers_title_and_description_of_visible_projects(self):
        response = self.client.get(self.url, {"q": "login"})
        self.assertCountEqual(self.titles(response), ["Login reparieren", "Export"])

    def test_key_search_finds_exact_item(self):
        response = self.client.get(self.url, {"q": f"srch-{self.match.number}"})
        self.assertEqual(self.titles(response), ["Login reparieren"])

    def test_archived_items_are_not_found(self):
        archive_item(self.match, actor=self.user)
        response = self.client.get(self.url, {"q": "reparieren"})
        self.assertEqual(self.titles(response), [])

    def test_short_queries_return_nothing(self):
        response = self.client.get(self.url, {"q": "l"})
        self.assertEqual(self.titles(response), [])

    def test_json_results_for_command_palette(self):
        response = self.client.get(
            self.url, {"q": "reparieren"}, HTTP_ACCEPT="application/json"
        )
        result = response.json()["results"][0]
        self.assertEqual(result["key"], self.match.key)
        self.assertEqual(result["title"], "Login reparieren")
        self.assertEqual(
            result["url"], reverse("backlog:detail", args=["SRCH", self.match.number])
        )


class SavedFilterTests(TestCase):
    def setUp(self):
        self.project = make_project("SAVE")
        self.anna = make_user()
        self.bert = make_user()
        add_member(self.project, self.anna)
        add_member(self.project, self.bert)
        self.list_url = reverse("backlog:list", args=["SAVE"])
        self.save_url = reverse("backlog:save_filter", args=["SAVE"])
        self.client.force_login(self.anna)

    def test_saving_keeps_only_known_filter_parameters(self):
        self.client.post(
            self.save_url,
            {"name": "Meine Bugs", "query": "type=bug&priority=high&evil=1&sort=key"},
        )
        saved = SavedFilter.objects.get()
        self.assertEqual(saved.query, "type=bug&priority=high&sort=key")
        self.assertEqual(saved.user, self.anna)
        response = self.client.get(self.list_url)
        self.assertContains(response, "Meine Bugs")
        self.assertContains(response, "?type=bug&amp;priority=high&amp;sort=key")

    def test_private_filters_are_hidden_from_colleagues(self):
        SavedFilter.objects.create(
            project=self.project, user=self.anna, name="Privat", query="type=bug"
        )
        SavedFilter.objects.create(
            project=self.project, user=self.anna, name="Team", query="type=task",
            shared=True,
        )
        self.client.force_login(self.bert)
        response = self.client.get(self.list_url)
        self.assertNotContains(response, "Privat")
        self.assertContains(response, "Team")

    def test_only_owner_deletes_filter(self):
        saved = SavedFilter.objects.create(
            project=self.project, user=self.anna, name="Weg", query="type=bug",
            shared=True,
        )
        delete_url = reverse("backlog:delete_filter", args=["SAVE", saved.pk])
        self.client.force_login(self.bert)
        self.assertEqual(self.client.post(delete_url).status_code, 404)
        self.client.force_login(self.anna)
        self.client.post(delete_url)
        self.assertFalse(SavedFilter.objects.exists())


class CommandPaletteTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.project = make_project("PAL")
        add_member(self.project, self.user)
        self.client.force_login(self.user)

    def test_pages_offer_palette_with_search_endpoint_and_shortcut_help(self):
        response = self.client.get(reverse("projects:detail", args=["PAL"]))
        search_url = reverse("core:search")
        self.assertContains(response, f'data-palette-url="{search_url}"')
        self.assertContains(response, 'id="palette-commands"')
        self.assertContains(response, 'id="shortcut-help"')

    def test_create_command_targets_current_project(self):
        self.client.get(reverse("backlog:list", args=["PAL"]))
        response = self.client.get(reverse("reporting:dashboard"))
        self.assertContains(response, reverse("backlog:create", args=["PAL"]))
