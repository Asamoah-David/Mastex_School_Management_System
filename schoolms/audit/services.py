from __future__ import annotations

import logging
from typing import Any, Optional

from audit.models import AuditLog

logger = logging.getLogger(__name__)


def write_audit(
    *,
    user,
    action: str,
    model_name: str,
    object_id: Optional[Any] = None,
    object_repr: Optional[str] = None,
    changes: Optional[dict] = None,
    request=None,
    school=None,
) -> None:
    """Central audit writer.

    This is intentionally thin and fails silently to preserve existing behavior.
    """
    try:
        AuditLog.log_action(
            user=user,
            action=action,
            model_name=model_name,
            object_id=object_id,
            object_repr=object_repr,
            changes=changes or {},
            request=request,
            school=school,
        )
    except Exception:
        logger.warning(
            "AuditLog write failed (action=%s model=%s object_id=%s)",
            action,
            model_name,
            object_id,
            exc_info=True,
        )
