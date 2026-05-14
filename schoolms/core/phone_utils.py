"""
Phone helpers for SMS (MNotify) and search.

Stored numbers may be ``0244…``, ``+233 24 …``, ``23324…``, or with spaces/dashes.
We normalize to digits-only international (Ghana default ``233``) for outbound SMS.
"""

from __future__ import annotations

import re
from typing import Optional

from django.db.models import Q

# Default country calling code when local Ghana numbers omit it (0XXXXXXXXX).
GHANA_CC = "233"


def digits_only(raw: Optional[str]) -> str:
    if raw is None:
        return ""
    return re.sub(r"\D", "", str(raw))


def normalize_phone_for_sms(raw: Optional[str], *, default_cc: str = GHANA_CC) -> str:
    """
    Return digits-only number suitable for MNotify ``recipient`` (no '+' prefix).

    - Strips spaces, dashes, parentheses.
    - ``0XXXXXXXXX`` (10 digits) → ``233`` + 9-digit national body.
    - ``233XXXXXXXXX`` kept as-is when already 12 digits.
    """
    d = digits_only(raw)
    if not d:
        return ""
    if len(d) == 10 and d.startswith("0"):
        return default_cc + d[1:]
    if len(d) == 9 and not d.startswith("0"):
        # Ambiguous; treat as national mobile without leading 0 (common typo)
        return default_cc + d
    if len(d) == 11 and d.startswith(default_cc) and d[3] == "0":
        # e.g. 2330XXXXXXXX → drop stray 0 after country code
        return default_cc + d[4:]
    return d


def phone_search_q(field_name: str, q: str) -> Q:
    """Build OR conditions so ``0244 123 456`` still matches ``0244123456`` in DB."""
    q = (q or "").strip()
    if not q:
        return Q(pk__in=[])
    variants = {q}
    d = digits_only(q)
    if d:
        variants.add(d)
        if len(d) == 12 and d.startswith(GHANA_CC):
            variants.add("0" + d[3:])
        elif len(d) == 10 and d.startswith("0"):
            variants.add(GHANA_CC + d[1:])
    out = Q()
    for v in variants:
        if v:
            out |= Q(**{f"{field_name}__icontains": v})
    return out
