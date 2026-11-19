from django.db import migrations


def watch_existing_items(apps, schema_editor):
    """Existing items get their creator and assignee as watchers."""
    BacklogItem = apps.get_model("backlog", "BacklogItem")
    ItemWatch = apps.get_model("notifications", "ItemWatch")
    watches = set()
    for item_id, created_by_id, assignee_id in BacklogItem.objects.values_list(
        "id", "created_by_id", "assignee_id"
    ):
        for user_id in (created_by_id, assignee_id):
            if user_id:
                watches.add((user_id, item_id))
    ItemWatch.objects.bulk_create(
        [ItemWatch(user_id=user_id, item_id=item_id) for user_id, item_id in watches],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0001_initial"),
        ("backlog", "0003_item_links"),
    ]

    operations = [
        migrations.RunPython(watch_existing_items, migrations.RunPython.noop),
    ]
