from django.conf import settings
from django.db import models

DECK = ("0", "1", "2", "3", "5", "8", "13", "20", "40", "100", "?", "☕")
NUMERIC_CARDS = tuple(int(card) for card in DECK if card.isdigit())


class PokerSession(models.Model):
    """Estimation round for one backlog item."""

    class Status(models.TextChoices):
        VOTING = "voting", "Abstimmung läuft"
        REVEALED = "revealed", "Aufgedeckt"
        CLOSED = "closed", "Abgeschlossen"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="poker_sessions"
    )
    item = models.ForeignKey(
        "backlog.BacklogItem", on_delete=models.CASCADE, related_name="poker_sessions"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="+",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.VOTING
    )
    round = models.PositiveSmallIntegerField(default=1)
    final_points = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-pk"]
        verbose_name = "Planning-Poker-Runde"
        verbose_name_plural = "Planning-Poker-Runden"
        constraints = [
            models.UniqueConstraint(
                fields=["item"],
                condition=~models.Q(status="closed"),
                name="poker_one_open_session_per_item",
            )
        ]

    def __str__(self) -> str:
        return f"Poker {self.item.key}"

    @property
    def is_open(self) -> bool:
        return self.status != self.Status.CLOSED


class PokerVote(models.Model):
    session = models.ForeignKey(
        PokerSession, on_delete=models.CASCADE, related_name="votes"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    value = models.CharField(max_length=4)
    voted_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session", "user"], name="poker_one_vote_per_user"
            )
        ]
