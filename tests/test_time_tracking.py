from datetime import date

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.backlog.models import BacklogItem, WorkLog
from apps.backlog.services import delete_work_log, log_work
from apps.backlog.timeparse import format_minutes, parse_duration
from apps.projects.models import ProjectMembership
from tests.factories import add_member, make_item, make_project, make_user

Access = ProjectMembership.AccessLevel


class DurationParsingTests(SimpleTestCase):
    def test_accepted_formats(self):
        cases = {
            "2h": 120, "45m": 45, "1h 30m": 90, "1d": 480, "1,5h": 90,
            "1.5h": 90, "2h15": 135, " 90 ": 90, "1d 2h": 600, "3 h 5 min": 185,
        }
        for text, minutes in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_duration(text), minutes)

    def test_invalid_input_is_rejected(self):
        for text in ("", "abc", "0", "-2h", "2x", "h"):
            with self.subTest(text=text), self.assertRaises(ValidationError):
                parse_duration(text)

    def test_formatting(self):
        self.assertEqual(format_minutes(90), "1h 30m")
        self.assertEqual(format_minutes(480), "1d")
        self.assertEqual(format_minutes(525), "1d 45m")
        self.assertEqual(format_minutes(0), "0m")
        self.assertEqual(format_minutes(None), "–")


class WorkLogServiceTests(TestCase):
    def setUp(self):
        self.project = make_project("TIME")
        self.dev = make_user()
        add_member(self.project, self.dev, access_level=Access.EDIT)
        self.item = make_item(
            self.project, original_estimate=480, remaining_estimate=480
        )

    def test_logging_reduces_remaining_estimate(self):
        log_work(self.item, self.dev, minutes=90, work_date=date(2026, 11, 18))
        self.item.refresh_from_db()
        self.assertEqual(self.item.time_spent, 90)
        self.assertEqual(self.item.remaining_estimate, 390)

    def test_remaining_never_drops_below_zero(self):
        log_work(self.item, self.dev, minutes=600, work_date=date(2026, 11, 18))
        self.item.refresh_from_db()
        self.assertEqual(self.item.remaining_estimate, 0)

    def test_remaining_can_be_set_explicitly(self):
        log_work(
            self.item, self.dev, minutes=60, work_date=date(2026, 11, 18),
            remaining=120,
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.remaining_estimate, 120)

    def test_item_without_estimate_keeps_none(self):
        item = make_item(self.project)
        log_work(item, self.dev, minutes=30, work_date=date(2026, 11, 18))
        item.refresh_from_db()
        self.assertIsNone(item.remaining_estimate)
        self.assertEqual(item.time_spent, 30)

    def test_deleting_log_restores_remaining(self):
        log = log_work(self.item, self.dev, minutes=60, work_date=date(2026, 11, 18))
        delete_work_log(log, actor=self.dev)
        self.item.refresh_from_db()
        self.assertEqual(self.item.time_spent, 0)
        self.assertEqual(self.item.remaining_estimate, 480)

    def test_minutes_must_be_positive(self):
        with self.assertRaises(ValidationError):
            log_work(self.item, self.dev, minutes=0, work_date=date(2026, 11, 18))
        self.assertFalse(WorkLog.objects.exists())

    def test_time_progress(self):
        log_work(self.item, self.dev, minutes=120, work_date=date(2026, 11, 18))
        self.item.refresh_from_db()
        progress = self.item.time_progress
        self.assertEqual(progress["spent_percent"], 25)
        self.assertFalse(progress["over_estimate"])


class WorkLogViewTests(TestCase):
    def setUp(self):
        self.project = make_project("TIME")
        self.dev = make_user()
        self.reader = make_user()
        self.other = make_user()
        add_member(self.project, self.dev, access_level=Access.EDIT)
        add_member(self.project, self.other, access_level=Access.EDIT)
        add_member(self.project, self.reader, access_level=Access.READ)
        self.item = make_item(
            self.project, original_estimate=240, remaining_estimate=240
        )
        self.url = reverse("backlog:log_work", args=["TIME", self.item.number])

    def test_editor_logs_time_from_text(self):
        self.client.force_login(self.dev)
        self.client.post(
            self.url,
            {"duration": "1h 30m", "work_date": "2026-11-18", "comment": "Review"},
        )
        log = WorkLog.objects.get()
        self.assertEqual((log.minutes, log.user, log.comment), (90, self.dev, "Review"))
        detail = self.client.get(
            reverse("backlog:detail", args=["TIME", self.item.number])
        )
        self.assertContains(detail, "Zeiterfassung")
        self.assertContains(detail, "1h 30m")

    def test_reader_cannot_log_time(self):
        self.client.force_login(self.reader)
        response = self.client.post(
            self.url, {"duration": "1h", "work_date": "2026-11-18"}
        )
        self.assertEqual(response.status_code, 403)

    def test_invalid_duration_is_reported(self):
        self.client.force_login(self.dev)
        self.client.post(self.url, {"duration": "viel", "work_date": "2026-11-18"})
        self.assertFalse(WorkLog.objects.exists())

    def test_only_author_deletes_own_log(self):
        log = log_work(self.item, self.dev, minutes=30, work_date=date(2026, 11, 18))
        delete_url = reverse(
            "backlog:delete_work_log", args=["TIME", self.item.number, log.pk]
        )
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(delete_url).status_code, 403)
        self.client.force_login(self.dev)
        self.client.post(delete_url)
        self.assertFalse(WorkLog.objects.exists())

    def test_estimate_is_entered_as_text_in_item_form(self):
        lead = make_user()
        add_member(self.project, lead, access_level=Access.MANAGE)
        self.client.force_login(lead)
        response = self.client.post(
            reverse("backlog:create", args=["TIME"]),
            {
                "item_type": BacklogItem.ItemType.TASK,
                "title": "Geschaetzt",
                "priority": BacklogItem.Priority.MEDIUM,
                "status": BacklogItem.Status.TODO,
                "original_estimate": "1d 4h",
            },
        )
        self.assertEqual(response.status_code, 302)
        item = BacklogItem.objects.get(title="Geschaetzt")
        self.assertEqual(item.original_estimate, 720)
        self.assertEqual(item.remaining_estimate, 720)
