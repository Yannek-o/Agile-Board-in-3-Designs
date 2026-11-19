"""Creates illustrative demo data for local reviews. Never use in production."""

import getpass
from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.backlog.models import BacklogItem
from apps.backlog.services import change_item_status, create_backlog_item
from apps.projects.models import Label, Project, ProjectMembership
from apps.sprints.services import add_item_to_sprint, create_sprint, start_sprint

Access = ProjectMembership.AccessLevel
Role = ProjectMembership.ScrumRole
Status = BacklogItem.Status
Priority = BacklogItem.Priority
ItemType = BacklogItem.ItemType

DEMO_USERS = [
    ("anna", "Anna", "S.", "Product Owner", Role.PRODUCT_OWNER, Access.MANAGE),
    ("ben", "Ben", "A.", "Entwicklung", Role.DEVELOPER, Access.EDIT),
    ("clara", "Clara", "L.", "Scrum Master", Role.SCRUM_MASTER, Access.EDIT),
    ("david", "David", "A.", "Entwicklung", Role.DEVELOPER, Access.READ),
]

HELPDESK_ITEMS = [
    ("Ticketstatus ändern und protokollieren", ItemType.STORY, Priority.HIGH, 5,
     "ben", Status.IN_PROGRESS),
    ("Ticketkategorien verwalten", ItemType.STORY, Priority.HIGH, 3,
     "anna", Status.TODO),
    ("Fehler bei Dateianhängen beheben", ItemType.BUG, Priority.HIGH, 2,
     "clara", Status.IN_REVIEW),
    ("E-Mail-Vorlagen konfigurieren", ItemType.STORY, Priority.MEDIUM, 5,
     "ben", Status.TODO),
    ("Login-Formular erstellen", ItemType.STORY, Priority.MEDIUM, 5,
     "ben", Status.DONE),
    ("Basis-Datenmodell umsetzen", ItemType.TECHNICAL, Priority.MEDIUM, 3,
     "anna", Status.DONE),
    ("Suchfunktion optimieren", ItemType.TECHNICAL, Priority.MEDIUM, 3, None,
     Status.TODO),
    ("Barrierefreie Formularfelder", ItemType.STORY, Priority.LOW, 2, None,
     Status.TODO),
    ("Ticket-Export als CSV", ItemType.TASK, Priority.LOW, 3, None, Status.TODO),
]


class Command(BaseCommand):
    help = "Legt Demo-Mitarbeiter, Projekte, Backlog und einen aktiven Sprint an."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            help="Passwort für alle Demo-Konten (sonst interaktive Abfrage).",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo-Daten nur mit DJANGO_DEBUG=true anlegen.")
        if Project.objects.filter(key="HELP").exists():
            raise CommandError("Demo-Daten existieren bereits.")
        password = options["password"] or getpass.getpass(
            "Passwort für Demo-Konten: "
        )
        if len(password) < 10:
            raise CommandError("Das Passwort muss mindestens 10 Zeichen haben.")

        with transaction.atomic():
            users = self.create_users(password)
            self.create_helpdesk(users)
            for key, name, status in (
                ("SHOP", "Webshop Relaunch", Project.Status.ACTIVE),
                ("DATA", "Datenimport-Tool", Project.Status.IN_REVIEW),
            ):
                project = Project.objects.create(
                    key=key, name=name, status=status,
                    created_by=users["anna"], description="Demo-Projekt",
                )
                for username, *_details, role, access in DEMO_USERS:
                    ProjectMembership.objects.create(
                        project=project, user=users[username],
                        scrum_role=role, access_level=access,
                    )
                create_backlog_item(
                    project, actor=users["anna"], title="Erste Anforderung",
                    assignee=users["david"], priority=Priority.HIGH,
                )
        self.stdout.write(
            self.style.SUCCESS("Demo-Daten angelegt. Konten: " + ", ".join(users))
        )

    def create_users(self, password: str) -> dict[str, User]:
        users = {}
        for username, first_name, last_name, job_title, *_ in DEMO_USERS:
            users[username] = User.objects.create_user(
                username=username,
                password=password,
                first_name=first_name,
                last_name=last_name,
                job_title=job_title,
                email=f"{username}@example.com",
                is_staff=username == "anna",
            )
        return users

    def create_helpdesk(self, users: dict[str, User]) -> None:
        owner = users["anna"]
        project = Project.objects.create(
            key="HELP",
            name="Internal Helpdesk",
            status=Project.Status.ACTIVE,
            created_by=owner,
            description="Ticketverwaltung, Service-Katalog und Support-Prozesse.",
            product_goal="Tickets zuverlässig erfassen und ihren "
            "Bearbeitungsstatus jederzeit nachvollziehbar verfolgen.",
            definition_of_done="Code reviewed\nAutomatisierte Tests grün\n"
            "Akzeptanzkriterien erfüllt\nDokumentation aktualisiert",
        )
        for username, *_details, role, access in DEMO_USERS:
            ProjectMembership.objects.create(
                project=project,
                user=users[username],
                scrum_role=role,
                access_level=access,
                can_manage_backlog=username == "ben",
            )
        frontend = Label.objects.create(
            project=project, name="Frontend", color="#e8912d"
        )
        backend = Label.objects.create(
            project=project, name="Backend", color="#5b9bd5"
        )
        today = date.today()
        sprint = create_sprint(
            project,
            actor=owner,
            goal="Tickets verlässlich bearbeiten und Status nachvollziehen",
            start_date=today - timedelta(days=2),
            end_date=today + timedelta(days=11),
        )
        create_sprint(
            project,
            actor=owner,
            goal="",
            start_date=today + timedelta(days=12),
            end_date=today + timedelta(days=25),
        )
        for index, entry in enumerate(HELPDESK_ITEMS):
            title, item_type, priority, points, assignee, status = entry
            item = create_backlog_item(
                project,
                actor=owner,
                title=title,
                item_type=item_type,
                priority=priority,
                story_points=points,
                assignee=users[assignee] if assignee else None,
                labels=[frontend] if index % 2 else [backend],
                acceptance_criteria=[
                    "Verhalten ist getestet",
                    "Änderung ist dokumentiert",
                ],
            )
            if index < 6:
                add_item_to_sprint(sprint, item, actor=owner)
            if status != Status.TODO:
                change_item_status(item, status, actor=users["ben"])
        start_sprint(sprint, actor=owner)
