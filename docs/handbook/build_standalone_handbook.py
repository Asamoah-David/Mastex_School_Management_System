#!/usr/bin/env python3
"""
Embed interface-tour PNGs from docs/handbook/images/ into index.html as data URLs.

This avoids broken screenshots when recipients open the HTML from a zip, from email,
or in environments where relative file paths to images/ fail.

Run from repo root:
    python docs/handbook/build_standalone_handbook.py

The management command capture_handbook_screenshots invokes this after saving PNGs
(unless --no-embed).
"""
from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
INDEX = HERE / "index.html"
IMAGES = HERE / "images"

# (filename, exact alt= value on the matching <img> in index.html)
FIGURES: tuple[tuple[str, str], ...] = (
    (
        "01-leadership-dashboard.png",
        "Mastex SchoolOS — leadership dashboard with sidebar navigation and metric cards.",
    ),
    (
        "02-school-fees.png",
        "Mastex SchoolOS school fees list with balances.",
    ),
    (
        "03-parent-fees.png",
        "Mastex SchoolOS parent school fees and Paystack payment.",
    ),
    (
        "04-sign-in.png",
        "Mastex SchoolOS sign in page.",
    ),
    (
        "05-notifications.png",
        "Mastex SchoolOS notification bell and inbox preview.",
    ),
)


def embed_tour_images_into_index() -> bool:
    text = INDEX.read_text(encoding="utf-8")
    original = text
    for fname, alt in FIGURES:
        png = IMAGES / fname
        if not png.is_file():
            continue
        uri = "data:image/png;base64," + base64.standard_b64encode(png.read_bytes()).decode("ascii")
        pattern = (
            r'(<img class="product-fig__shot" src=")[^"]+(" alt="'
            + re.escape(alt)
            + r'" width="1200" height="675" decoding="async" />)'
        )

        def _repl(m: re.Match, u: str = uri) -> str:
            return m.group(1) + u + m.group(2)

        text, _n = re.subn(pattern, _repl, text, count=1)
    if text == original:
        return False
    INDEX.write_text(text, encoding="utf-8")
    return True


def main() -> int:
    if not INDEX.is_file():
        print(f"Missing {INDEX}", file=sys.stderr)
        return 1
    if embed_tour_images_into_index():
        print(f"Updated {INDEX} with embedded interface-tour PNGs.")
        return 0
    print(
        "No changes: save PNGs under docs/handbook/images/ or fix alt text / img markup.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
