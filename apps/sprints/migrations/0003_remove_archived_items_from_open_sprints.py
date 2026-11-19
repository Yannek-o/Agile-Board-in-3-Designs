from django.db import migrations
from django.utils import timezone

OPEN_SPRINT_STATUSES = ("planned", "active")


def remove_archived_items_from_open_sprints(apps, schema_editor):
    SprintItem = apps.get_model("sprints", "SprintItem")
    SprintItem.objects.filter(
        outcome="open",
        sprint__status__in=OPEN_SPRINT_STATUSES,
        item__archived_at__isnull=False,
    ).update(outcome="removed", closed_at=timezone.now())


class Migration(migrations.Migration):

    dependencies = [
        ("backlog", "0005_epic_color"),
        ("sprints", "0002_sprint_retro_actions_sprint_retro_to_improve_and_more"),
    ]

    operations = [
        migrations.RunPython(
            remove_archived_items_from_open_sprints, migrations.RunPython.noop
        ),
    ]
