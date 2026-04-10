#!/usr/bin/env python
"""
One-off audit: template {% url %} names vs URLconf, and render() template paths vs files.
Run from repo root: python scripts/audit_system.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Repo root (parent of scripts/)
ROOT = Path(__file__).resolve().parent.parent
SCHOOLMS = ROOT / "schoolms"
TEMPLATES = SCHOOLMS / "templates"
sys.path.insert(0, str(SCHOOLMS.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolms.settings")

import django  # noqa: E402

django.setup()

from django.apps import apps  # noqa: E402
from django.template.loader import get_template  # noqa: E402
from django.template.exceptions import TemplateDoesNotExist  # noqa: E402
from django.urls import NoReverseMatch, reverse  # noqa: E402


def collect_url_tags() -> set[str]:
    """First argument of {% url '...' %} only (static names)."""
    pat = re.compile(r"\{%\s*url\s+['\"]([^'\"]+)['\"]")
    names: set[str] = set()
    for f in TEMPLATES.rglob("*.html"):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in pat.finditer(text):
            names.add(m.group(1).strip())
    return names


def try_reverse(name: str) -> bool:
    if ":" not in name:
        candidates = [
            {},
            {"pk": 1},
            {"id": 1},
            {"fee_id": 1},
            {"student_id": 1},
            {"homework_id": 1},
            {"exam_id": 1},
            {"student_pk": 1},
        ]
    else:
        candidates = [
            {},
            {"pk": 1},
            {"id": 1},
        ]
    for kwargs in candidates:
        try:
            reverse(name, kwargs=kwargs)
            return True
        except NoReverseMatch:
            continue
        except TypeError:
            continue
    # Positional args (slug, action)
    for args in [
        (1,),
        (1, "approve"),
        ("canteen", 1),
        ("bus", 1),
        ("textbook", 1),
    ]:
        try:
            reverse(name, args=args)
            return True
        except NoReverseMatch:
            continue
        except TypeError:
            continue
    return False


def collect_render_templates() -> set[str]:
    """Literal template strings in render(request, '...')."""
    pat = re.compile(r"render\s*\(\s*request\s*,\s*['\"]([^'\"]+)['\"]")
    found: set[str] = set()
    for py in SCHOOLMS.rglob("*.py"):
        if "migrations" in py.parts or "venv" in py.parts:
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in pat.finditer(text):
            found.add(m.group(1))
    return found


def template_exists(name: str) -> bool:
    try:
        get_template(name)
        return True
    except TemplateDoesNotExist:
        return False


def main() -> int:
    print("=== Django system check ===")
    from django.core.management import call_command

    try:
        call_command("check", verbosity=0)
        print("check: OK")
    except django.core.management.base.SystemCheckError as e:
        print("check: FAILED\n", e)
        return 1

    print("\n=== {% url %} reverse audit (static names only) ===")
    url_names = collect_url_tags()
    bad_urls = sorted(n for n in url_names if not try_reverse(n))
    if bad_urls:
        print(f"FAILED: {len(bad_urls)} name(s) could not be reversed with common args:")
        for n in bad_urls:
            print(f"  - {n}")
    else:
        print(f"OK: {len(url_names)} static url tag(s) reversed successfully.")

    print("\n=== render() template file resolution ===")
    render_names = collect_render_templates()
    missing_tpl = sorted(t for t in render_names if not template_exists(t))
    if missing_tpl:
        print(f"FAILED: {len(missing_tpl)} template(s) missing:")
        for t in missing_tpl:
            print(f"  - {t}")
    else:
        print(f"OK: {len(render_names)} render() template path(s) resolve.")

    print("\n=== Installed apps (sample) ===")
    print(", ".join(sorted(apps.app_configs.keys())))

    return 1 if (bad_urls or missing_tpl) else 0


if __name__ == "__main__":
    sys.exit(main())
