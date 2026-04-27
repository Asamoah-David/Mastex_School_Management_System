"""
Feature-flag enforcement for views.

Usage examples
--------------
Function-based view::

    from core.feature_access import feature_required

    @feature_required("hostel")
    def hostel_list(request):
        ...

Class-based view mixin::

    from core.feature_access import FeatureRequiredMixin

    class HostelListView(FeatureRequiredMixin, ListView):
        required_features = ["hostel"]
        ...

Multiple features (all must be enabled)::

    @feature_required("online_payments", "fee_management")
    def pay_fee(request):
        ...
"""
from __future__ import annotations

import functools
import logging
from typing import Sequence

from django.http import HttpResponseForbidden
from django.shortcuts import render

logger = logging.getLogger(__name__)

_DISABLED_TEMPLATE = "core/feature_disabled.html"


def _feature_disabled_response(request, features: Sequence[str]):
    """Return a 403 response explaining which feature is disabled."""
    ctx = {"disabled_features": features}
    try:
        return render(request, _DISABLED_TEMPLATE, ctx, status=403)
    except Exception:
        return HttpResponseForbidden(
            f"This feature ({', '.join(features)}) is not enabled for your school."
        )


def _check_features(request, features: Sequence[str]) -> list[str]:
    """Return list of disabled feature keys, empty if all enabled."""
    school = getattr(request, "school", None)
    if school is None:
        return []
    return [f for f in features if not school.has_feature(f)]


def feature_required(*features: str):
    """View decorator that blocks access when any of ``features`` is disabled.

    Expects ``request.school`` to be set by :class:`~schools.middleware.SchoolMiddleware`.
    If ``request.school`` is ``None`` (super-admin context) access is always allowed.
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapped(request, *args, **kwargs):
            disabled = _check_features(request, features)
            if disabled:
                logger.info(
                    "Feature gate blocked %s for school=%s features=%s",
                    request.path,
                    getattr(getattr(request, "school", None), "pk", None),
                    disabled,
                )
                return _feature_disabled_response(request, disabled)
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


class FeatureRequiredMixin:
    """CBV mixin that enforces feature flags before dispatching.

    Set ``required_features`` as a list/tuple of feature key strings on
    the class.  Missing or empty list means no enforcement (always pass).
    """

    required_features: Sequence[str] = []

    def dispatch(self, request, *args, **kwargs):
        disabled = _check_features(request, self.required_features)
        if disabled:
            logger.info(
                "Feature gate blocked %s for school=%s features=%s",
                request.path,
                getattr(getattr(request, "school", None), "pk", None),
                disabled,
            )
            return _feature_disabled_response(request, disabled)
        return super().dispatch(request, *args, **kwargs)
