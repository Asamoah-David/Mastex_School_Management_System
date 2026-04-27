"""
Unit tests for multi-guardian notification logic (_get_guardians).
Run with: pytest core/tests_multi_guardian.py -v
"""
from unittest.mock import MagicMock, patch, PropertyMock
from django.test import TestCase


class GetGuardiansTests(TestCase):
    """Tests for core.signals._get_guardians()."""

    def _make_student(self, parent=None):
        student = MagicMock()
        student.parent = parent
        return student

    def test_returns_primary_guardians_from_through_table(self):
        from core.signals import _get_guardians

        g1 = MagicMock()
        g2 = MagicMock()

        with patch("students.models.StudentGuardian") as MockSG, \
             patch("django.contrib.auth.get_user_model") as mock_get_user_model:
            MockSG.objects.filter.return_value.select_related.return_value.values_list.return_value = [1, 2]
            User = MagicMock()
            User.objects.filter.return_value = [g1, g2]
            mock_get_user_model.return_value = User

            student = self._make_student()
            result = _get_guardians(student)
            assert result == [g1, g2]

    def test_falls_back_to_legacy_parent_when_no_guardian_rows(self):
        from core.signals import _get_guardians

        parent = MagicMock()
        student = self._make_student(parent=parent)

        with patch("students.models.StudentGuardian") as MockSG:
            MockSG.objects.filter.return_value.select_related.return_value.values_list.return_value = []

            result = _get_guardians(student)
            assert result == [parent]

    def test_returns_empty_when_no_guardian_and_no_parent(self):
        from core.signals import _get_guardians

        student = self._make_student(parent=None)

        with patch("students.models.StudentGuardian") as MockSG:
            MockSG.objects.filter.return_value.select_related.return_value.values_list.return_value = []

            result = _get_guardians(student)
            assert result == []

    def test_handles_import_error_gracefully(self):
        """If StudentGuardian import fails, fall back to legacy parent."""
        from core.signals import _get_guardians

        parent = MagicMock()
        student = self._make_student(parent=parent)

        with patch("students.models.StudentGuardian", side_effect=Exception("import error")):
            result = _get_guardians(student)
            assert result == [parent]


class TenantIsolationTests(TestCase):
    """
    Verify cross-tenant clean() guards on HostelAssignment, HostelFee, BusPayment.
    These are pure model validation tests — no real DB rows needed.
    """

    def _make_obj(self, model_cls, **kwargs):
        obj = model_cls.__new__(model_cls)
        for k, v in kwargs.items():
            setattr(obj, k, v)
        return obj

    def test_hostel_assignment_rejects_cross_tenant_student(self):
        from django.core.exceptions import ValidationError
        from operations.models.hostel import HostelAssignment

        obj = HostelAssignment()
        obj.school_id = 1
        obj.student_id = 99
        obj.hostel_id = None
        obj.room_id = None

        student = MagicMock()
        student.school_id = 2  # Different school!
        obj._state.fields_cache['student'] = student  # inject into Django 5 FK cache

        with self.assertRaises(ValidationError) as ctx:
            obj.clean()
        assert "student" in str(ctx.exception).lower() or "Student" in str(ctx.exception)

    def test_hostel_assignment_passes_same_tenant(self):
        from operations.models.hostel import HostelAssignment

        obj = HostelAssignment()
        obj.school_id = 1
        obj.student_id = 5
        obj.hostel_id = None
        obj.room_id = None

        student = MagicMock()
        student.school_id = 1  # Same school ✓
        obj._state.fields_cache['student'] = student  # inject into Django 5 FK cache

        obj.clean()  # Should not raise

    def test_bus_payment_rejects_cross_tenant_route(self):
        from django.core.exceptions import ValidationError
        from operations.models.transport import BusPayment

        obj = BusPayment()
        obj.school_id = 1
        obj.student_id = None
        obj.route_id = 10

        route = MagicMock()
        route.school_id = 2  # Different school!
        obj._state.fields_cache['route'] = route  # inject into Django 5 FK cache

        with self.assertRaises(ValidationError) as ctx:
            obj.clean()
        assert "route" in str(ctx.exception).lower() or "Route" in str(ctx.exception)

    def test_hostel_fee_rejects_cross_tenant_hostel(self):
        from django.core.exceptions import ValidationError
        from operations.models.hostel import HostelFee

        obj = HostelFee()
        obj.school_id = 1
        obj.student_id = None
        obj.hostel_id = 7

        hostel = MagicMock()
        hostel.school_id = 3  # Different school!
        obj._state.fields_cache['hostel'] = hostel  # inject into Django 5 FK cache

        with self.assertRaises(ValidationError) as ctx:
            obj.clean()
        assert "hostel" in str(ctx.exception).lower() or "Hostel" in str(ctx.exception)
