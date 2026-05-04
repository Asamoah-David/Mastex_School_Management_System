"""
Unit tests for School.has_feature() and the feature_access module.
Uses Django TestCase so the School model is accessible.
Run with: pytest schools/tests_feature_flags.py -v
"""
import pytest
from django.test import TestCase, RequestFactory
from unittest.mock import MagicMock, patch


class SchoolHasFeatureTests(TestCase):
    """Test School.has_feature() with mocked DB queries.

    The implementation uses a bulk ``values_list("key", "enabled")`` query
    whose result is stored in Django's shared cache (TTL 300 s).  Tests must
    therefore mock ``features.values_list`` (not ``filter/values/first``) and
    clear the cache between runs.
    """

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()

    def _make_school(self):
        from schools.models import School
        school = MagicMock()
        school.pk = 1
        school.features = MagicMock()
        # Bind ALL required methods so internal cross-calls work correctly.
        school._feature_cache_key = School._feature_cache_key
        school._load_feature_map = School._load_feature_map.__get__(school, School)
        school.has_feature = School.has_feature.__get__(school, School)
        school.has_features = School.has_features.__get__(school, School)
        school.invalidate_feature_cache = School.invalidate_feature_cache.__get__(school, School)
        return school

    def test_missing_row_defaults_to_enabled(self):
        school = self._make_school()
        school.features.values_list.return_value = []
        assert school.has_feature("hostel") is True

    def test_enabled_row_returns_true(self):
        school = self._make_school()
        school.features.values_list.return_value = [("library", True)]
        assert school.has_feature("library") is True

    def test_disabled_row_returns_false(self):
        school = self._make_school()
        school.features.values_list.return_value = [("canteen", False)]
        assert school.has_feature("canteen") is False

    def test_instance_cache_prevents_double_query(self):
        school = self._make_school()
        school.features.values_list.return_value = [("hostel", True)]
        school.has_feature("hostel")
        school.has_feature("hostel")
        # Second call must hit Django cache — DB queried only once.
        assert school.features.values_list.call_count == 1

    def test_invalidate_cache_clears_results(self):
        from django.core.cache import cache
        from schools.models import School
        school = self._make_school()
        school.features.values_list.return_value = [("hostel", True)]
        school.has_feature("hostel")
        cache_key = School._feature_cache_key(school.pk)
        assert cache.get(cache_key) is not None, "Cache should be populated after has_feature()"
        school.invalidate_feature_cache()
        assert cache.get(cache_key) is None, "Cache should be cleared after invalidate_feature_cache()"

    def test_has_features_all_enabled(self):
        school = self._make_school()
        school.features.values_list.return_value = [
            ("hostel", True), ("library", True), ("canteen", True),
        ]
        assert school.has_features("hostel", "library", "canteen") is True

    def test_has_features_one_disabled(self):
        school = self._make_school()
        school.features.values_list.return_value = [
            ("hostel", True), ("library", False),
        ]
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
