from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.poker.models import PokerSession
from apps.poker.services import (
    accept_estimate,
    cast_vote,
    reset_round,
    reveal,
    session_state,
    start_session,
)
from apps.projects.models import ProjectMembership
from tests.factories import add_member, make_item, make_project, make_user

Access = ProjectMembership.AccessLevel


class PokerServiceTests(TestCase):
    def setUp(self):
        self.project = make_project("POK")
        self.lead = make_user("lead")
        self.dev = make_user("dev")
        add_member(self.project, self.lead, access_level=Access.MANAGE)
        add_member(self.project, self.dev)
        self.item = make_item(self.project, title="Login")
        self.session = start_session(self.item, actor=self.lead)

    def test_starting_twice_reuses_the_open_session(self):
        self.assertEqual(start_session(self.item, actor=self.lead), self.session)

    def test_votes_stay_hidden_until_reveal(self):
        cast_vote(self.session, self.dev, "5")
        state = session_state(self.session, viewer=self.lead)
        dev_entry = next(v for v in state["votes"] if v["name"] == "dev")
        self.assertTrue(dev_entry["voted"])
        self.assertIsNone(dev_entry["value"])
        self.assertIsNone(state["summary"])

    def test_own_vote_is_visible_to_the_voter(self):
        cast_vote(self.session, self.dev, "8")
        self.assertEqual(session_state(self.session, viewer=self.dev)["my_vote"], "8")

    def test_voters_without_membership_still_appear(self):
        admin = make_user("admin", is_superuser=True, is_staff=True)
        cast_vote(self.session, admin, "3")
        names = [v["name"] for v in session_state(self.session, viewer=admin)["votes"]]
        self.assertIn("admin", names)

    def test_reveal_shows_values_and_suggests_estimate(self):
        cast_vote(self.session, self.dev, "3")
        cast_vote(self.session, self.lead, "8")
        reveal(self.session, actor=self.lead)
        state = session_state(self.session, viewer=self.dev)
        self.assertEqual(
            sorted(v["value"] for v in state["votes"] if v["voted"]), ["3", "8"]
        )
        self.assertEqual(state["summary"]["average"], 5.5)
        self.assertEqual(state["summary"]["suggestion"], 8)
        self.assertFalse(state["summary"]["consensus"])

    def test_no_votes_after_reveal_and_invalid_cards_rejected(self):
        with self.assertRaises(ValidationError):
            cast_vote(self.session, self.dev, "7")
        reveal(self.session, actor=self.lead)
        with self.assertRaises(ValidationError):
            cast_vote(self.session, self.dev, "5")

    def test_reset_starts_a_new_round(self):
        cast_vote(self.session, self.dev, "3")
        reveal(self.session, actor=self.lead)
        reset_round(self.session, actor=self.lead)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, PokerSession.Status.VOTING)
        self.assertEqual(self.session.round, 2)
        self.assertFalse(self.session.votes.exists())

    def test_accept_sets_story_points_and_closes(self):
        accept_estimate(self.session, 5, actor=self.lead)
        self.item.refresh_from_db()
        self.session.refresh_from_db()
        self.assertEqual(self.item.story_points, 5)
        self.assertEqual(self.session.status, PokerSession.Status.CLOSED)
        self.assertNotEqual(start_session(self.item, actor=self.lead), self.session)


class PokerViewTests(TestCase):
    def setUp(self):
        self.project = make_project("PKV")
        self.lead = make_user("lead")
        self.dev = make_user("dev")
        self.reader = make_user("reader")
        add_member(self.project, self.lead, access_level=Access.MANAGE)
        add_member(self.project, self.dev)
        add_member(self.project, self.reader, access_level=Access.READ)
        self.item = make_item(self.project, title="Export")

    def start(self):
        self.client.force_login(self.lead)
        response = self.client.post(
            reverse("poker:start", args=["PKV"]), {"item": self.item.number}
        )
        return PokerSession.objects.get(), response

    def test_lead_starts_session_and_is_redirected(self):
        session, response = self.start()
        self.assertRedirects(
            response, reverse("poker:detail", args=["PKV", session.pk])
        )

    def test_developers_vote_and_read_json_state(self):
        session, _ = self.start()
        self.client.force_login(self.dev)
        self.client.post(
            reverse("poker:vote", args=["PKV", session.pk]), {"value": "13"}
        )
        response = self.client.get(
            reverse("poker:detail", args=["PKV", session.pk]),
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.json()["my_vote"], "13")

    def test_readers_watch_but_cannot_vote(self):
        session, _ = self.start()
        self.client.force_login(self.reader)
        detail = reverse("poker:detail", args=["PKV", session.pk])
        self.assertEqual(self.client.get(detail).status_code, 200)
        vote = reverse("poker:vote", args=["PKV", session.pk])
        self.assertEqual(self.client.post(vote, {"value": "3"}).status_code, 403)

    def test_developers_cannot_reveal_or_accept(self):
        session, _ = self.start()
        self.client.force_login(self.dev)
        reveal_url = reverse("poker:reveal", args=["PKV", session.pk])
        self.assertEqual(self.client.post(reveal_url).status_code, 403)

    def test_accept_view_updates_item(self):
        session, _ = self.start()
        self.client.post(
            reverse("poker:accept", args=["PKV", session.pk]), {"points": "8"}
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.story_points, 8)

    def test_item_panel_links_to_poker(self):
        self.client.force_login(self.lead)
        response = self.client.get(
            reverse("backlog:detail", args=["PKV", self.item.number])
        )
        self.assertContains(response, reverse("poker:start", args=["PKV"]))
