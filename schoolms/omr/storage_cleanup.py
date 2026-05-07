"""
Shared helpers to prune OMR files from local MEDIA_ROOT (not DB rows).

Remote storage (e.g. S3): configure bucket lifecycle rules separately.
"""

from __future__ import annotations

import time
from pathlib import Path

from django.conf import settings


def prune_omr_directory(
    subdir: str,
    *,
    older_than_hours: float,
    dry_run: bool = False,
) -> tuple[int, int, list[str]]:
    """
    Delete files under MEDIA_ROOT/omr/<subdir>/ older than cutoff.

    Returns (deleted_count, kept_count, errors).
    """
    root = Path(getattr(settings, "MEDIA_ROOT", "")) / "omr" / subdir
    if not root.is_dir():
        return 0, 0, []

    cutoff = time.time() - older_than_hours * 3600
    deleted = 0
    kept = 0
    errors: list[str] = []

    for fpath in root.iterdir():
        if not fpath.is_file():
            continue
        try:
            if fpath.stat().st_mtime < cutoff:
                if dry_run:
                    deleted += 1
                else:
                    fpath.unlink()
                    deleted += 1
            else:
                kept += 1
        except OSError as exc:
            errors.append(f"{fpath.name}: {exc}")

    return deleted, kept, errors
