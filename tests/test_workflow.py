from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.backlog.models import AcceptanceCriterion, BacklogItem
from apps.backlog.services import change_item_status
from apps.projects.models import ProjectMembership
from apps.sprints.services import add_item_to_sprint, start_sprint
from tests.factories import add_member, make_item, make_project, make_sprint, make_user

Access = ProjectMembership.AccessLevel
Role = ProjectMembership.ScrumRole
Status = BacklogItem.Status


class WorkflowRuleTests(TestCase):
    def setUp(self):
        self.project = make_project("FLOW")
        self.lead = make_user()
        self.dev = make_user()
        self.owner = make_user()
        add_member(self.project, self.lead, access_level=Access.MANAGE)
        add_member(self.project, self.dev, access_level=Access.EDIT)
        add_member(
            self.project, self.owner, access_level=Access.EDIT,
            scrum_role=Role.PRODUCT_OWNER,
        )
        self.item = make_item(self.project)

    def configure(self, **settings):
        for field, value in settings.items():
            setattr(self.project, field, value)
        self.project.save()
        self.item.refresh_from_db()

    def test_without_rules_every_transition_is_allowed(self):
        change_item_status(self.item, Status.DONE, actor=self.dev)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, Status.DONE)

    def test_review_is_mandatory_before_done(self):
        self.configure(require_review=True)
        with self.assertRaisesMessage(ValidationError, "In Review"):
            change_item_status(self.item, Status.DONE, actor=self.lead)
        change_item_status(self.item, Status.IN_REVIEW, actor=self.dev)
        change_item_status(self.item, Status.DONE, actor=self.dev)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, Status.DONE)

    def test_only_lead_or_product_owner_may_finish(self):
        self.configure(done_requires_lead=True)
        with self.assertRaises(ValidationError):
            change_item_status(self.item, Status.DONE, actor=self.dev)
        change_item_status(self.item, Status.DONE, actor=self.owner)
        other = make_item(self.project)
        change_item_status(other, Status.DONE, actor=self.lead)

    def test_done_needs_met_acceptance_criteria(self):
        self.configure(done_requires_criteria=True)
        criterion = AcceptanceCriterion.objects.create(
            item=self.item, text="Getestet", position=1
        )
        with self.assertRaisesMessage(ValidationError, "Akzeptanzkriterien"):
            change_item_status(self.item, Status.DONE, actor=self.dev)
        criterion.is_met = True
        criterion.save()
        change_item_status(self.item, Status.DONE, actor=self.dev)

    def test_reopening_is_not_restricted(self):
        change_item_status(self.item, Status.DONE, actor=self.dev)
        self.configure(require_review=True, done_requires_lead=True)
        change_item_status(self.item, Status.TODO, actor=self.dev)

    def test_disabled_review_column_cannot_be_used(self):
        self.configure(use_review_column=False)
        with self.assertRaises(ValidationError):
            change_item_status(self.item, Status.IN_REVIEW, actor=self.dev)

    def test_review_requirement_needs_review_column(self):
        self.project.use_review_column = False
        self.project.require_review = True
        with self.assertRaises(ValidationError):
            self.project.full_clean()


class WorkflowBoardTests(TestCase):
    def setUp(self):
        self.project = make_project(
            "FLOW", status_label_todo="Offen", status_label_done="Ausgeliefert"
        )
        self.dev = make_user()
        add_member(self.project, self.dev, access_level=Access.EDIT)
        lead = make_user()
        add_member(self.project, lead, access_level=Access.MANAGE)
        sprint = make_sprint(self.project)
        self.item = make_item(self.project)
        add_item_to_sprint(sprint, self.item, actor=lead)
        start_sprint(sprint, actor=lead)
        self.board_url = reverse("board:board", args=["FLOW"])
        self.client.force_login(self.dev)

    def test_board_uses_project_labels(self):
        response = self.client.get(self.board_url)
        labels = [column["label"] for column in response.context["columns"]]
        self.assertEqual(labels, ["Offen", "In Progress", "In Review", "Ausgeliefert"])

    def test_disabled_review_column_is_hidden(self):
        self.project.use_review_column = False
        self.project.save()
        response = self.client.get(self.board_url)
        statuses = [column["status"] for column in response.context["columns"]]
        self.assertNotIn(Status.IN_REVIEW, statuses)
        self.assertNotIn(
            Status.IN_REVIEW, [value for value, _ in response.context["status_choices"]]
        )

    def test_rejected_move_explains_the_rule(self):
        self.project.require_review = True
        self.project.save()
        response = self.client.post(
            reverse("board:move", args=["FLOW"]),
            {"item": self.item.number, "version": self.item.version, "status": "done"},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("In Review", response.json()["error"])

    def test_project_form_saves_workflow(self):
        lead = make_user()
        add_member(self.project, lead, access_level=Access.MANAGE)
        self.client.force_login(lead)
        response = self.client.post(
            reverse("projects:edit", args=["FLOW"]),
            {
                "name": self.project.name,
                "status": self.project.status,
                "status_label_todo": "Backlog",
                "status_label_in_progress": "",
                "status_label_in_review": "Test",
                "status_label_done": "",
                "use_review_column": "on",
                "require_review": "on",
                "done_requires_lead": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status_label("todo"), "Backlog")
        self.assertEqual(self.project.status_label("done"), "Done")
        self.assertTrue(self.project.require_review)
        self.assertTrue(self.project.done_requires_lead)
        self.assertFalse(self.project.done_requires_criteria)
