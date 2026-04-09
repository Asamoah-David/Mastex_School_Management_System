"""
Scan HTML templates for {% url 'name' %} tags and verify names reverse.

Usage:
    python manage.py audit_urls
"""

import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import NoReverseMatch, reverse

# Static view name in {% url 'namespace:name' %} or {% url "name" %}
_URL_NAME_RE = re.compile(r"\{%\s*url\s+['\"]([a-zA-Z0-9_:.-]+)['\"]")


def _iter_template_files(base: Path):
    skip = {"node_modules", "staticfiles", "__pycache__", ".git", "migrations"}
    for path in base.rglob("*.html"):
        if any(part in skip for part in path.parts):
            continue
        yield path


def _try_reverse(name: str):
    try:
        reverse(name)
        return True, ""
    except NoReverseMatch:
        pass
    dummy_kwarg_sets = (
        {"pk": 1},
        {"id": 1},
        {"slug": "x"},
        {"fee_id": 1},
        {"student_id": 1},
        {"subject_id": 1},
        {"meeting_id": 1},
        {"homework_id": 1},
        {"exam_id": 1},
        {"attempt_id": 1},
        {"payment_type": "fee", "payment_id": 1},
        {"pk": 1, "decision": "approve"},
        {"class_name": "x"},
        {"username": "x"},
    )
    for kwargs in dummy_kwarg_sets:
        try:
            reverse(name, kwargs=kwargs)
            return True, f"requires path args (verified with kwargs={kwargs})"
        except NoReverseMatch:
            continue
    return False, "NoReverseMatch (missing args or unknown name)"


class Command(BaseCommand):
    help = "Find {% url %} names in templates and check they resolve with reverse()"

    def handle(self, *args, **options):
        base = settings.BASE_DIR
        names_found: set[str] = set()
        for path in _iter_template_files(base):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                self.stderr.write(f"Skip {path}: {exc}")
                continue
            for m in _URL_NAME_RE.finditer(text):
                names_found.add(m.group(1))

        if not names_found:
            self.stdout.write(self.style.WARNING("No static {% url '...' %} names found."))
            return

        bad = []
        ok = []
        for name in sorted(names_found):
            success, detail = _try_reverse(name)
            if success:
                ok.append((name, detail))
            else:
                bad.append((name, detail))

        self.stdout.write(self.style.MIGRATE_HEADING(f"\n  Template URL audit ({len(names_found)} unique names)\n"))
        for name, detail in ok:
            if detail:
                self.stdout.write(f"  OK  {name}  — {detail}")
            else:
                self.stdout.write(f"  OK  {name}")

        for name, detail in bad:
            self.stdout.write(self.style.ERROR(f"  BAD {name}  — {detail}"))

        if bad:
            self.stderr.write(self.style.ERROR(f"\n{len(bad)} name(s) could not be reversed."))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS(f"\nAll {len(ok)} resolvable (or satisfied with dummy kwargs)."))
