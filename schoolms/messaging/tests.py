"""Feature gates and tenancy helpers for messaging."""

import uuid

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from schools.models import School, SchoolFeature


class MessagingFeatureGateTests(TestCase):
    """School-scoped messaging URLs require SchoolFeature('messaging')."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Msg Gate School", subdomain=f"msg-gate-{uuid.uuid4().hex[:10]}")
        SchoolFeature.objects.update_or_create(
            school=cls.school, key="messaging", defaults={"enabled": False}
        )
        cls.admin = User.objects.create_user(
            username="msg_gate_admin", password="pw12345", school=cls.school, role="school_admin"
        )
        cls.teacher = User.objects.create_user(
            username="msg_gate_teacher", password="pw12345", school=cls.school, role="teacher"
        )

    def setUp(self):
        self.client = Client()

    def test_send_message_redirects_when_messaging_disabled(self):
        self.client.login(username="msg_gate_admin", password="pw12345")
        r = self.client.get(reverse("messaging:send_message"))
        self.assertRedirects(r, reverse("accounts:dashboard"), fetch_redirect_response=False)

    def test_message_history_redirects_when_messaging_disabled(self):
        self.client.login(username="msg_gate_admin", password="pw12345")
        r = self.client.get(reverse("messaging:message_history"))
        self.assertRedirects(r, reverse("accounts:dashboard"), fetch_redirect_response=False)

    def test_bulk_sms_redirects_when_messaging_disabled(self):
        self.client.login(username="msg_gate_admin", password="pw12345")
        r = self.client.get(reverse("messaging:bulk_sms_page"))
        self.assertRedirects(r, reverse("accounts:dashboard"), fetch_redirect_response=False)

    def test_sms_history_redirects_when_messaging_disabled(self):
        self.client.login(username="msg_gate_admin", password="pw12345")
        r = self.client.get(reverse("messaging:sms_history"))
        self.assertRedirects(r, reverse("accounts:dashboard"), fetch_redirect_response=False)

    def test_chat_view_redirects_when_messaging_disabled(self):
        self.client.login(username="msg_gate_teacher", password="pw12345")
        r = self.client.get(reverse("messaging:chat_view"))
        self.assertRedirects(r, reverse("accounts:dashboard"), fetch_redirect_response=False)

    def test_get_recipients_returns_403_when_messaging_disabled(self):
        self.client.login(username="msg_gate_admin", password="pw12345")
        r = self.client.get(reverse("messaging:get_recipients"), {"type": "all_parents"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json().get("error"), "feature_disabled")
