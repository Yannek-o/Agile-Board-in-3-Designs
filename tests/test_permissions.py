from django.test import TestCase

from apps.projects.models import ProjectMembership
from apps.projects.permissions import get_project_access, visible_projects
from tests.factories import add_member, make_admin, make_project, make_user

Access = ProjectMembership.AccessLevel


class ProjectAccessMatrixTests(TestCase):
    def setUp(self):
        self.project = make_project("HELP")

    def access_for(self, user):
        return get_project_access(user, self.project)

    def test_system_admin_has_all_rights_without_membership(self):
        access = self.access_for(make_admin())
        self.assertTrue(access.can_view)
        self.assertTrue(access.can_manage_project)
        self.assertTrue(access.can_manage_backlog)
        self.assertTrue(access.can_change_status)

    def test_project_lead_manages_own_project(self):
        lead = make_user()
        add_member(self.project, lead, access_level=Access.MANAGE)
        access = self.access_for(lead)
        self.assertTrue(access.can_manage_project)
        self.assertTrue(access.can_manage_backlog)
        self.assertTrue(access.can_change_status)
        self.assertTrue(access.can_comment)

    def test_editor_without_approval_cannot_plan(self):
        editor = make_user()
        add_member(self.project, editor, access_level=Access.EDIT)
        access = self.access_for(editor)
        self.assertTrue(access.can_view)
        self.assertFalse(access.can_manage_project)
        self.assertFalse(access.can_manage_backlog)
        self.assertTrue(access.can_change_status)

    def test_editor_with_approval_can_plan(self):
        editor = make_user()
        add_member(
            self.project, editor, access_level=Access.EDIT,
            can_manage_backlog=True,
        )
        self.assertTrue(self.access_for(editor).can_manage_backlog)

    def test_read_only_member_can_only_view(self):
        reader = make_user()
        add_member(
            self.project, reader, access_level=Access.READ,
            can_manage_backlog=True,
        )
        access = self.access_for(reader)
        self.assertTrue(access.can_view)
        self.assertFalse(access.can_manage_backlog)
        self.assertFalse(access.can_change_status)
        self.assertFalse(access.can_comment)

    def test_scrum_role_does_not_grant_technical_rights(self):
        product_owner = make_user()
        add_member(
            self.project,
            product_owner,
            access_level=Access.READ,
            scrum_role=ProjectMembership.ScrumRole.PRODUCT_OWNER,
        )
        self.assertFalse(self.access_for(product_owner).can_manage_backlog)

    def test_non_member_and_inactive_member_have_no_access(self):
        self.assertFalse(self.access_for(make_user()).can_view)
        former = make_user()
        add_member(self.project, former, is_active=False)
        self.assertFalse(self.access_for(former).can_view)

    def test_deactivated_user_has_no_access(self):
        user = make_user(is_active=False)
        add_member(self.project, user, access_level=Access.MANAGE)
        self.assertFalse(self.access_for(user).can_view)

    def test_visible_projects_contains_only_memberships(self):
        user = make_user()
        other = make_project("OTHER")
        add_member(self.project, user)
        self.assertEqual(list(visible_projects(user)), [self.project])
        self.assertEqual(
            set(visible_projects(make_admin())), {self.project, other}
        )
