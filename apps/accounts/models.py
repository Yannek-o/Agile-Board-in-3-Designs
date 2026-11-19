from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower

AVATAR_COLOR_VALIDATOR = RegexValidator(
    r"^#[0-9a-f]{6}$", "Bitte eine Farbe im Format #rrggbb wählen."
)
DARK_AVATAR_TEXT = "#1a1a1a"
LIGHT_AVATAR_TEXT = "#ffffff"
# (colour, optional gradient colour, label) offered as quick picks in the user menu
AVATAR_PRESETS = (
    ("#ff6b00", "", "Orange"),
    ("#e11d48", "", "Rot"),
    ("#2563eb", "", "Blau"),
    ("#0d9488", "", "Petrol"),
    ("#16a34a", "", "Grün"),
    ("#ff6b00", "#8b5cf6", "Verlauf Orange–Violett"),
    ("#ec4899", "#8b5cf6", "Verlauf Pink–Violett"),
    ("#3fd4c4", "#d98a4e", "Verlauf Petrol–Kupfer"),
)


def relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance of a #rrggbb colour."""
    channels = []
    for index in (1, 3, 5):
        value = int(hex_color[index:index + 2], 16) / 255
        channels.append(
            value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
        )
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


class User(AbstractUser):
    """Employee account."""

    class Design(models.TextChoices):
        NEON = "neon", "Neon"
        PATINA = "patina", "Patina"
        KALT = "kalt", "Kalt"

    email = models.EmailField("E-Mail-Adresse", blank=True)
    job_title = models.CharField("Funktion", max_length=120, blank=True)
    can_create_projects = models.BooleanField(
        "Darf Projekte anlegen",
        default=False,
        help_text="Erlaubt das Anlegen neuer Projekte ohne Systemadministration.",
    )
    email_notifications = models.BooleanField(
        "E-Mail-Benachrichtigungen",
        default=True,
        help_text="Zuweisungen, Kommentare und Sprint-Ereignisse per E-Mail.",
    )
    dashboard_notes = models.TextField("Notizen", blank=True, max_length=5000)
    design = models.CharField(
        "Design",
        max_length=20,
        choices=Design.choices,
        default=Design.NEON,
        help_text="Persönliche Wahl der Oberfläche; Funktionen sind identisch.",
    )
    avatar_color = models.CharField(
        "Avatar-Farbe", max_length=7, blank=True, validators=[AVATAR_COLOR_VALIDATOR]
    )
    avatar_color_2 = models.CharField(
        "Avatar-Verlaufsfarbe",
        max_length=7,
        blank=True,
        validators=[AVATAR_COLOR_VALIDATOR],
        help_text="Optional: zweite Farbe für einen Verlauf.",
    )

    class Meta:
        ordering = ["first_name", "last_name", "username"]
        verbose_name = "Mitarbeiter"
        verbose_name_plural = "Mitarbeiter"
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                condition=~models.Q(email=""),
                name="accounts_user_unique_email_ci",
            )
        ]

    def __str__(self) -> str:
        return self.display_name

    @property
    def display_name(self) -> str:
        return self.get_full_name() or self.username

    @property
    def initials(self) -> str:
        if self.first_name and self.last_name:
            return f"{self.first_name[0]}{self.last_name[0]}".upper()
        return self.display_name[:2].upper()

    @property
    def is_system_admin(self) -> bool:
        return self.is_active and (self.is_superuser or self.is_staff)

    @property
    def may_create_projects(self) -> bool:
        return self.is_active and (self.is_system_admin or self.can_create_projects)

    @property
    def avatar_background(self) -> str:
        """CSS background of the avatar; empty means the design's default."""
        if not self.avatar_color:
            return ""
        if not self.avatar_color_2:
            return self.avatar_color
        return (
            f"linear-gradient(135deg, {self.avatar_color} 0%, "
            f"{self.avatar_color_2} 100%)"
        )

    @property
    def avatar_text_color(self) -> str:
        colors = [color for color in (self.avatar_color, self.avatar_color_2) if color]
        if not colors:
            return LIGHT_AVATAR_TEXT
        luminance = sum(relative_luminance(color) for color in colors) / len(colors)
        # Above this luminance dark text has the higher contrast ratio.
        return DARK_AVATAR_TEXT if luminance > 0.179 else LIGHT_AVATAR_TEXT


class AccountEvent(models.Model):
    """Audit trail of administrative changes to employee accounts."""

    class Action(models.TextChoices):
        CREATED = "created", "Angelegt"
        INVITED = "invited", "Einladung gesendet"
        UPDATED = "updated", "Geändert"
        DEACTIVATED = "deactivated", "Deaktiviert"
        ACTIVATED = "activated", "Aktiviert"

    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="account_events"
    )
    user_label = models.CharField(max_length=150)
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    details = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "Kontoänderung"
        verbose_name_plural = "Kontoänderungen"

    def __str__(self) -> str:
        return f"{self.user_label}: {self.get_action_display()}"


class AuthAttempt(models.Model):
    """Records security-relevant attempts used for throttling."""

    class Kind(models.TextChoices):
        LOGIN_FAILURE = "login_failure", "Fehlgeschlagene Anmeldung"
        PASSWORD_RESET = "password_reset", "Passwort-Reset angefordert"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    username = models.CharField(max_length=150, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Anmeldeversuch"
        verbose_name_plural = "Anmeldeversuche"

    def __str__(self) -> str:
        return f"{self.get_kind_display()} · {self.username or self.ip_address}"
