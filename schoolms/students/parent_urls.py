"""
Parent portal URL namespace — /parent/...

All parent-facing views are accessible here under a clean, role-specific prefix.
This makes RBAC and CSP policy simpler and gives parents a consistent URL space.

Mirrors the views already declared in students/views.py; no duplication.
"""
from django.urls import path
from .views import (
    parent_dashboard,
    parent_child_detail,
    fees_list,
    results_list,
    announcements_list,
    parent_absence_request_create,
    parent_absence_requests,
)

app_name = "parent"

urlpatterns = [
    # Dashboard — /parent/
    path("", parent_dashboard, name="dashboard"),
    # Per-child detail — /parent/children/<pk>/
    path("children/<int:pk>/", parent_child_detail, name="child_detail"),
    # Fee summary — /parent/fees/
    path("fees/", fees_list, name="fees"),
    # Results (published) — /parent/results/
    path("results/", results_list, name="results"),
    # Announcements — /parent/announcements/
    path("announcements/", announcements_list, name="announcements"),
    # Absence requests — /parent/absence/
    path("absence/", parent_absence_requests, name="absence_list"),
    path("absence/request/", parent_absence_request_create, name="absence_request"),
]
