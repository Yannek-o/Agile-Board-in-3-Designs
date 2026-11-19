"""Lightweight object factories shared by the test suite."""

import itertools
from datetime import date, timedelta

from apps.accounts.models import User
from apps.backlog.models import BacklogItem
from apps.backlog.services import create_backlog_item
from apps.projects.models import Project, ProjectMembership
from apps.sprints.models import Sprint
from apps.sprints.services import create_sprint

DEFAULT_PASSWORD = "Sicheres-Passwort-2026"
_sequence = itertools.count(1)


def make_user(username: str | None = None, **extra) -> User:
    username = username or f"user{next(_sequence)}"
    extra.setdefault("email", f"{username}@example.com")
    return User.objects.create_user(
        username=username, password=DEFAULT_PASSWORD, **extra
    )


def make_admin(username: str = "admin") -> User:
    return make_user(username, is_staff=True, is_superuser=True)


def make_project(key: str | None = None, **extra) -> Project:
    key = key or f"P{next(_sequence)}"
    extra.setdefault("name", f"Projekt {key}")
    extra.setdefault("status", Project.Status.ACTIVE)
    return Project.objects.create(key=key, **extra)


def add_member(
    project: Project,
    user: User,
    access_level: str = ProjectMembership.AccessLevel.EDIT,
    scrum_role: str = ProjectMembership.ScrumRole.DEVELOPER,
    **extra,
) -> ProjectMembership:
    return ProjectMembership.objects.create(
        project=project,
        user=user,
        access_level=access_level,
        scrum_role=scrum_role,
        **extra,
    )


def make_item(project: Project, actor: User | None = None, **fields) -> BacklogItem:
    fields.setdefault("title", f"Eintrag {next(_sequence)}")
    return create_backlog_item(project=project, actor=actor, **fields)


def make_sprint(
    project: Project, actor: User | None = None, **fields
) -> Sprint:
    start = fields.pop("start_date", date(2026, 11, 16))
    end = fields.pop("end_date", start + timedelta(days=13))
    fields.setdefault("goal", "Sprint-Ziel")
    return create_sprint(
        project=project, actor=actor, start_date=start, end_date=end, **fields
    )
