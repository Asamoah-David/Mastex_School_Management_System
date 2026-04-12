from datetime import timedelta

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from core.subscription_access import (
    subscription_grace_days_for_school,
    subscription_hard_block_applies,
    subscription_in_grace_period,
)


class _School:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class SubscriptionAccessTests(SimpleTestCase):
    def test_grace_days_fallback(self):
        s = _School(subscription_grace_days=3)
        self.assertEqual(subscription_grace_days_for_school(s), 3)
        with override_settings(SUBSCRIPTION_DEFAULT_GRACE_DAYS=14):
            s2 = _School(subscription_grace_days=None)
            self.assertEqual(subscription_grace_days_for_school(s2), 14)

    def test_hard_block_cancelled(self):
        s = _School(subscription_status="cancelled", subscription_end_date=None)
        self.assertTrue(subscription_hard_block_applies(s))

    def test_hard_block_after_grace(self):
        now = timezone.now()
        end = now - timedelta(days=10)
        s = _School(subscription_status="active", subscription_end_date=end)
        with override_settings(SUBSCRIPTION_DEFAULT_GRACE_DAYS=7):
            self.assertTrue(subscription_hard_block_applies(s, now=now))

    def test_no_block_within_grace(self):
        now = timezone.now()
        end = now - timedelta(days=3)
        s = _School(subscription_status="active", subscription_end_date=end)
        with override_settings(SUBSCRIPTION_DEFAULT_GRACE_DAYS=7):
            self.assertFalse(subscription_hard_block_applies(s, now=now))
            self.assertTrue(subscription_in_grace_period(s, now=now))
