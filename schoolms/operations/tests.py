"""Operations workflows: admissions pipeline, etc."""

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from operations.models import AdmissionApplication
from schools.models import School


class AdmissionPipelineViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Ops Pipe School", subdomain="ops-pipe-sch-01")
        cls.admin = User.objects.create_user(
            username="ops_pipe_admin",
            password="pw12345",
            school=cls.school,
            role="school_admin",
        )
        cls.app = AdmissionApplication.objects.create(
            public_reference="ADM-TESTPIPE01",
            school=cls.school,
            first_name="A",
            last_name="B",
            date_of_birth="2015-01-01",
            gender="male",
            class_applied_for="1A",
            parent_first_name="P",
            parent_last_name="Q",
            parent_phone="0240000001",
            parent_email="p@example.com",
            address="Addr",
            status="pending",
        )

    def setUp(self):
        self.client = Client()

    def test_set_status_moves_pipeline(self):
        self.client.login(username="ops_pipe_admin", password="pw12345")
        url = reverse("operations:admission_set_status", args=[self.app.pk])
        r = self.client.post(url, {"status": "under_review"})
        self.assertEqual(r.status_code, 302)
        self.app.refresh_from_db()
        self.assertEqual(self.app.status, "under_review")

    def test_pipeline_board_renders(self):
        self.client.login(username="ops_pipe_admin", password="pw12345")
        r = self.client.get(reverse("operations:admission_pipeline"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Table view")
