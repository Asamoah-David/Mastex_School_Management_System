"""
Unit tests for School.has_feature() and the feature_access module.
Uses Django TestCase so the School model is accessible.
Run with: pytest schools/tests_feature_flags.py -v
"""
import pytest
from django.test import TestCase, RequestFactory
from unittest.mock import MagicMock, patch


class SchoolHasFeatureTests(TestCase):
    """Test School.has_feature() with mocked DB queries."""

    def _make_school(self):
        school = MagicMock()
        school.pk = 1
        # Simulate the features related manager
        school.features = MagicMock()
        # Remove _feature_cache so the method starts fresh
        if hasattr(school, "_feature_cache"):
            del school._feature_cache
        # Attach the real method from the class
        from schools.models import School
        school.has_feature = School.has_feature.__get__(school, School)
        school.has_features = School.has_features.__get__(school, School)
        school.invalidate_feature_cache = School.invalidate_feature_cache.__get__(school, School)
        return school

    def test_missing_row_defaults_to_enabled(self):
        school = self._make_school()
        school.features.filter.return_value.values.return_value.first.return_value = None
        assert school.has_feature("hostel") is True

    def test_enabled_row_returns_true(self):
        school = self._make_school()
        school.features.filter.return_value.values.return_value.first.return_value = {"enabled": True}
        assert school.has_feature("library") is True

    def test_disabled_row_returns_false(self):
        school = self._make_school()
        school.features.filter.return_value.values.return_value.first.return_value = {"enabled": False}
        assert school.has_feature("canteen") is False

    def test_instance_cache_prevents_double_query(self):
        school = self._make_school()
        school.features.filter.return_value.values.return_value.first.return_value = {"enabled": True}
        school.has_feature("hostel")
        school.has_feature("hostel")
        # DB query should only happen once
        assert school.features.filter.call_count == 1

    def test_invalidate_cache_clears_results(self):
        school = self._make_school()
        school.features.filter.return_value.values.return_value.first.return_value = {"enabled": True}
        school.has_feature("hostel")
        school.invalidate_feature_cache()
        # After invalidation, feature_cache should be empty
        assert school._feature_cache == {}

    def test_has_features_all_enabled(self):
        school = self._make_school()
        school.features.filter.return_value.values.return_value.first.return_value = {"enabled": True}
        assert school.has_features("hostel", "library", "canteen") is True

    def test_has_features_one_disabled(self):
        school = self._make_school()
        call_count = [0]

        def mock_first():
            call_count[0] += 1
            if call_count[0] == 2:
                return {"enabled": False}
            return {"enabled": True}

        school.features.filter.return_value.values.return_value.first = mock_first
        assert school.has_features("hostel", "library") is False


class FeatureRequiredDecoratorTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _make_request_with_school(self, feature_enabled):
        request = self.factory.get("/test/")
        request.user = MagicMock()
        request.user.is_authenticated = True
        school = MagicMock()
        school.has_feature = MagicMock(return_value=feature_enabled)
        request.school = school
        return request

    def test_allowed_when_feature_enabled(self):
        from core.feature_access import feature_required

        @feature_required("hostel")
        def dummy_view(request):
            return MagicMock(status_code=200)

        request = self._make_request_with_school(True)
        response = dummy_view(request)
        assert response.status_code == 200

    def test_blocked_when_feature_disabled(self):
        from core.feature_access import feature_required

        @feature_required("hostel")
        def dummy_view(request):
            return MagicMock(status_code=200)  # pragma: no cover

        request = self._make_request_with_school(False)
        response = dummy_view(request)
        assert response.status_code == 403

    def test_allowed_when_no_school_on_request(self):
        """Super-admin context: request.school is None → always allow."""
        from core.feature_access import feature_required

        @feature_required("hostel")
        def dummy_view(request):
            return MagicMock(status_code=200)

        request = self.factory.get("/test/")
        request.user = MagicMock()
        request.school = None
        response = dummy_view(request)
        assert response.status_code == 200
