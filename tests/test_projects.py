from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.projects.forms import ProjectForm
from apps.projects.models import Label, Project, ProjectMembership
from tests.factories import add_member, make_admin, make_project, make_user

Access = ProjectMembership.AccessLevel
Role = ProjectMembership.ScrumRole


class ProjectModelTests(TestCase):
    def test_project_key_is_unique(self):
        make_project("HELP")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_project("HELP")

    def test_membership_is_unique_per_project_and_user(self):
        project = make_project()
        user = make_user()
        add_member(project, user)
        with self.assertRaises(IntegrityError), transaction.atomic():
            add_member(project, user)

    def test_archived_projects_are_excluded_from_active_queryset(self):
        active = make_project("ACT")
        archived = make_project("ARC")
        archived.archive()
        self.assertIn(active, Project.objects.not_archived())
        self.assertNotIn(archived, Project.objects.not_archived())


class ProjectFormTests(TestCase):
    def form(self, **overrides):
        data = {
            "name": "Internal Helpdesk",
            "key": "help",
            "description": "",
            "product_goal": "Tickets zuverlässig bearbeiten",
            "definition_of_done": "Getestet und reviewed",
            "status": Project.Status.ACTIVE,
        }
        data.update(overrides)
        return ProjectForm(data=data)

    def test_key_is_normalized_to_upper_case(self):
        form = self.form()
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["key"], "HELP")

    def test_invalid_key_characters_are_rejected(self):
        self.assertFalse(self.form(key="HE LP").is_valid())
        self.assertFalse(self.form(key="1HELP").is_valid())
        self.assertFalse(self.form(key="H").is_valid())

    def test_duplicate_key_is_rejected_case_insensitively(self):
        make_project("HELP")
        form = self.form(key="Help")
        self.assertFalse(form.is_valid())
        self.assertIn("key", form.errors)


class ProjectViewTests(TestCase):
    def setUp(self):
        self.project = make_project("HELP", name="Internal Helpdesk")
        self.lead = make_user("lead")
        self.editor = make_user("editor")
        self.outsider = make_user("outsider")
        add_member(self.project, self.lead, access_level=Access.MANAGE)
        add_member(self.project, self.editor, access_level=Access.EDIT)

    def test_project_list_shows_only_accessible_projects(self):
        make_project("SECRET", name="Geheimes Projekt")
        self.client.force_login(self.editor)
        response = self.client.get(reverse("projects:list"))
        self.assertContains(response, "Internal Helpdesk")
        self.assertNotContains(response, "Geheimes Projekt")

    def test_project_list_filters_by_search_and_status(self):
        make_project("SHOP", name="Webshop Relaunch")
        self.client.force_login(make_admin())
        response = self.client.get(reverse("projects:list"), {"q": "SHOP"})
        self.assertContains(response, "Webshop Relaunch")
        self.assertNotContains(response, "Internal Helpdesk")

    def test_outsider_gets_404_for_foreign_project(self):
        self.client.force_login(self.outsider)
        response = self.client.get(reverse("projects:detail", args=["HELP"]))
        self.assertEqual(response.status_code, 404)

    def test_user_without_create_right_cannot_create_project(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse("projects:create"))
        self.assertEqual(response.status_code, 403)

    def test_authorized_user_creates_project_and_becomes_lead(self):
        creator = make_user("creator", can_create_projects=True)
        self.client.force_login(creator)
        response = self.client.post(
            reverse("projects:create"),
            {
                "name": "Datenimport-Tool",
                "key": "data",
                "description": "Preisdaten",
                "product_goal": "Preise korrekt exportieren",
                "definition_of_done": "Tests grün",
                "status": Project.Status.PLANNED,
            },
        )
        project = Project.objects.get(key="DATA")
        self.assertRedirects(
            response, reverse("projects:detail", args=["DATA"])
        )
        membership = project.memberships.get(user=creator)
        self.assertEqual(membership.access_level, Access.MANAGE)
        self.assertEqual(project.created_by, creator)

    def test_editor_cannot_edit_project(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse("projects:edit", args=["HELP"]), {"name": "Gehackt"}
        )
        self.assertEqual(response.status_code, 403)

    def test_lead_edits_project_but_key_is_immutable(self):
        self.client.force_login(self.lead)
        response = self.client.post(
            reverse("projects:edit", args=["HELP"]),
            {
                "name": "Helpdesk Neu",
                "key": "CHANGED",
                "description": "",
                "product_goal": "Neues Ziel",
                "definition_of_done": "DoD",
                "status": Project.Status.ACTIVE,
            },
        )
        self.assertRedirects(response, reverse("projects:detail", args=["HELP"]))
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "Helpdesk Neu")
        self.assertEqual(self.project.key, "HELP")

    def test_lead_archives_and_restores_project(self):
        self.client.force_login(self.lead)
        self.client.post(reverse("projects:archive", args=["HELP"]))
        self.project.refresh_from_db()
        self.assertIsNotNone(self.project.archived_at)
        self.client.post(reverse("projects:restore", args=["HELP"]))
        self.project.refresh_from_db()
        self.assertIsNone(self.project.archived_at)

    def test_archive_requires_post(self):
        self.client.force_login(self.lead)
        response = self.client.get(reverse("projects:archive", args=["HELP"]))
        self.assertEqual(response.status_code, 405)


class TeamManagementTests(TestCase):
    def setUp(self):
        self.project = make_project("HELP")
        self.lead = make_user("lead")
        self.editor = make_user("editor")
        self.lead_membership = add_member(
            self.project, self.lead, access_level=Access.MANAGE,
            scrum_role=Role.PRODUCT_OWNER,
        )
        self.editor_membership = add_member(self.project, self.editor)

    def test_lead_adds_member_with_separate_role_and_access(self):
        new_user = make_user("david")
        self.client.force_login(self.lead)
        response = self.client.post(
            reverse("projects:member_add", args=["HELP"]),
            {
                "user": new_user.pk,
                "scrum_role": Role.DEVELOPER,
                "access_level": Access.READ,
            },
        )
        self.assertRedirects(response, reverse("projects:team", args=["HELP"]))
        membership = self.project.memberships.get(user=new_user)
        self.assertEqual(membership.scrum_role, Role.DEVELOPER)
        self.assertEqual(membership.access_level, Access.READ)

    def test_inactive_users_cannot_be_added(self):
        inactive = make_user(is_active=False)
        self.client.force_login(self.lead)
        response = self.client.post(
            reverse("projects:member_add", args=["HELP"]),
            {
                "user": inactive.pk,
                "scrum_role": Role.DEVELOPER,
                "access_level": Access.READ,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.project.memberships.filter(user=inactive).exists())

    def test_editor_cannot_manage_team(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse("projects:member_edit", args=["HELP", self.editor_membership.pk]),
            {"scrum_role": Role.SCRUM_MASTER, "access_level": Access.MANAGE},
        )
        self.assertEqual(response.status_code, 403)
        self.editor_membership.refresh_from_db()
        self.assertEqual(self.editor_membership.access_level, Access.EDIT)

    def test_last_lead_cannot_be_demoted(self):
        self.client.force_login(self.lead)
        response = self.client.post(
            reverse("projects:member_edit", args=["HELP", self.lead_membership.pk]),
            {"scrum_role": Role.PRODUCT_OWNER, "access_level": Access.READ},
        )
        self.assertEqual(response.status_code, 200)
        self.lead_membership.refresh_from_db()
        self.assertEqual(self.lead_membership.access_level, Access.MANAGE)

    def test_last_lead_cannot_be_removed(self):
        self.client.force_login(self.lead)
        self.client.post(
            reverse(
                "projects:member_remove", args=["HELP", self.lead_membership.pk]
            )
        )
        self.lead_membership.refresh_from_db()
        self.assertTrue(self.lead_membership.is_active)

    def test_removing_member_deactivates_membership(self):
        self.client.force_login(self.lead)
        self.client.post(
            reverse(
                "projects:member_remove", args=["HELP", self.editor_membership.pk]
            )
        )
        self.editor_membership.refresh_from_db()
        self.assertFalse(self.editor_membership.is_active)

    def test_membership_of_other_project_is_not_reachable(self):
        other = make_project("OTHER")
        foreign = add_member(other, make_user())
        self.client.force_login(self.lead)
        response = self.client.post(
            reverse("projects:member_remove", args=["HELP", foreign.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_lead_manages_labels(self):
        self.client.force_login(self.lead)
        self.client.post(
            reverse("projects:labels", args=["HELP"]),
            {"name": "Frontend", "color": "#e67e22"},
        )
        label = Label.objects.get(project=self.project, name="Frontend")
        self.client.post(
            reverse("projects:label_delete", args=["HELP", label.pk])
        )
        self.assertFalse(Label.objects.filter(pk=label.pk).exists())
