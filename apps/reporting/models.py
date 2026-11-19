from django.conf import settings
from django.db import models


class DashboardSnapshot(models.Model):
    """Dashboard key figures of one user at the end of a day."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dashboard_snapshots",
    )
    day = models.DateField()
    metrics = models.JSONField(default=dict)

    class Meta:
        ordering = ["user", "day"]
        verbose_name = "Dashboard-Stand"
        verbose_name_plural = "Dashboard-Stände"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "day"], name="reporting_one_snapshot_per_day"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} · {self.day:%d.%m.%Y}"
