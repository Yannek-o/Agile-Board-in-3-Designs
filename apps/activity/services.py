from apps.activity.models import ActivityEvent


def record_event(
    project,
    action: str,
    actor=None,
    item=None,
    sprint=None,
    field: str = "",
    old_value: object = "",
    new_value: object = "",
    message: str = "",
) -> ActivityEvent:
    return ActivityEvent.objects.create(
        project=project,
        action=action,
        actor=actor if actor is not None and actor.is_authenticated else None,
        item=item,
        sprint=sprint,
        field=field,
        old_value="" if old_value is None else str(old_value),
        new_value="" if new_value is None else str(new_value),
        message=message[:255],
    )
