# OMR Production Guide

**Date:** 2026-05-06

## Runtime behaviour

| Setting | Purpose |
|---------|---------|
| `ENABLE_DEBUG_OVERLAYS` | If `false`, pipeline writes **no** debug PNGs (recommended production). |
| `OMR_SAVE_MINIMAL_DEBUG` | If overlays on + `true`, only overlay image; if `false`, full normalized/diff/blank set. |
| `KEEP_RAW_SCANS_DAYS` / `OMR_TEMP_RETENTION_HOURS` | Temp upload retention under `MEDIA_ROOT/omr/temp/`. |
| `KEEP_DEBUG_OVERLAYS_DAYS` / `OMR_DEBUG_RETENTION_HOURS` | Debug PNG retention under `MEDIA_ROOT/omr/debug/`. |
| `ENABLE_RAW_SCAN_STORAGE` | When `false`, temp retention is capped (short-lived scans). |
| `AUTO_CLEANUP_ENABLED` | When `false`, `cleanup_omr_media_files` Celery task skips work. |

## Operations

- **Schedule:** `core.tasks.cleanup_omr_media_files` daily via `CELERY_BEAT_SCHEDULE` (`cleanup-omr-media-daily`).
- **Manual:** `python manage.py cleanup_omr_images [--dry-run] [--hours N] [--debug-hours N]`
- **Object storage (S3):** The cleanup command only deletes local files under `MEDIA_ROOT`. Configure **S3 lifecycle** to expire `omr/debug/*` and `omr/temp/*` similarly.

## Quality pipeline (reference)

- Perspective correction and quality gate in `omr/pipeline.py`.
- Blank-template subtraction when calibration exists.
- Connected-component scoring; uncertain / multiple / blank flagged for review.
- Templates in `omr_templates_v2.py` — tune thresholds per exam board with care.

## Admin analytics (roadmap)

Track in DB or BI: average confidence, failure rate per template, manual correction counts. Current code stores rich per-question metadata in session/API responses; persist aggregates if ministry reporting requires them.

## Incident response

1. Disable overlays (`ENABLE_DEBUG_OVERLAYS=false`) to save disk.
2. Shorten retention env vars and run `cleanup_omr_images`.
3. Re-run affected exams from saved answer keys after template fix.

---

*See also `SYSTEM_AUDIT.md` § OMR.*
