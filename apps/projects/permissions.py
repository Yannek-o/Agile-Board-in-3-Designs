"""Server-side project permission rules.

Scrum accountabilities never grant technical rights; only the access level
of an active membership (or system administration) does.
"""

from dataclasses import dataclass

from django.db.models import QuerySet

from apps.projects.models import Project, ProjectMembership

Access = ProjectMembership.AccessLevel


@dataclass(frozen=True)
class ProjectAccess:
    project: Project
    membership: ProjectMembership | None
    is_system_admin: bool

    @property
    def access_level(self) -> str | None:
        if self.is_system_admin:
            return Access.MANAGE
        return self.membership.access_level if self.membership else None

    @property
    def can_view(self) -> bool:
        return self.access_level is not None

    @property
    def can_manage_project(self) -> bool:
        return self.access_level == Access.MANAGE

    @property
    def can_manage_backlog(self) -> bool:
        if self.access_level == Access.MANAGE:
            return True
        return (
            self.access_level == Access.EDIT
            and self.membership is not None
            and self.membership.can_manage_backlog
        )

    @property
    def can_change_status(self) -> bool:
        return self.access_level in (Access.MANAGE, Access.EDIT)

    @property
    def can_comment(self) -> bool:
        return self.can_change_status

    @property
    def is_read_only(self) -> bool:
        return self.access_level == Access.READ


def get_project_access(user, project: Project) -> ProjectAccess:
    if not user.is_authenticated or not user.is_active:
        return ProjectAccess(project, None, False)
    if user.is_system_admin:
        return ProjectAccess(project, None, True)
    membership = ProjectMembership.objects.filter(
        project=project, user=user, is_active=True
    ).first()
    return ProjectAccess(project, membership, False)


def visible_projects(user) -> QuerySet[Project]:
    if not user.is_authenticated or not user.is_active:
        return Project.objects.none()
    if user.is_system_admin:
        return Project.objects.all()
    return Project.objects.filter(
        memberships__user=user, memberships__is_active=True
    ).distinct()
