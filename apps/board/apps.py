from django.apps import AppConfig


class BoardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.board"
    label = "board"
    verbose_name = "Agile Board"
