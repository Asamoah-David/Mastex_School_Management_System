"""
Capture real PNG screenshots into docs/handbook/images/ and embed them in index.html.

Uses a temporary SQLite database, migrates, seeds demo data, starts runserver on a
free port, then Playwright (Chromium). Does not modify your normal DATABASE_URL.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from .handbook_seed_demo import DEFAULT_PASSWORD

REPO_ROOT = Path(__file__).resolve().parents[4]
MANAGE_PY = REPO_ROOT / "manage.py"
HANDBOOK_DIR = REPO_ROOT / "docs" / "handbook"
INDEX_HTML = HANDBOOK_DIR / "index.html"
IMAGES_DIR = HANDBOOK_DIR / "images"

ADMIN_USER = "handbook_admin"
PARENT_USER = "handbook_parent"


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    _, port = s.getsockname()
    s.close()
    return port


def _capture_with_playwright(base_url: str, password: str) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise CommandError(
            "Playwright is not installed. Run:\n"
            "  pip install -r docs/handbook/requirements-capture.txt\n"
            "  python -m playwright install chromium\n"
        ) from e

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    def wait_login_splash_gone(pg) -> None:
        # base_login.html shows a full-screen splash ~650ms; it intercepts clicks until .hidden.
        pg.wait_for_selector("#splashScreen.hidden", timeout=15000)

    def login(pg, username: str) -> None:
        pg.goto(f"{base_url}/accounts/login/", wait_until="domcontentloaded")
        wait_login_splash_gone(pg)
        pg.fill('input[name="username"]', username)
        pg.fill('input[name="password"]', password)
        pg.click('button[type="submit"]')
        pg.wait_for_load_state("domcontentloaded")
        time.sleep(0.9)

    def logout(pg) -> None:
        pg.goto(f"{base_url}/accounts/logout/", wait_until="domcontentloaded")
        time.sleep(0.4)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            device_scale_factor=1,
        )
        page = context.new_page()

        page.goto(f"{base_url}/accounts/login/", wait_until="domcontentloaded")
        wait_login_splash_gone(page)
        time.sleep(0.35)
        page.screenshot(path=str(IMAGES_DIR / "04-sign-in.png"), full_page=False)

        login(page, ADMIN_USER)
        for fname, path in (
            ("01-leadership-dashboard.png", "/accounts/school-dashboard/"),
            ("02-school-fees.png", "/finance/fees/"),
            ("05-notifications.png", "/notifications/"),
        ):
            page.goto(f"{base_url}{path}", wait_until="domcontentloaded")
            time.sleep(0.75)
            page.screenshot(path=str(IMAGES_DIR / fname), full_page=False)
        logout(page)

        login(page, PARENT_USER)
        page.goto(f"{base_url}/finance/my-fees/", wait_until="domcontentloaded")
        time.sleep(0.75)
        page.screenshot(path=str(IMAGES_DIR / "03-parent-fees.png"), full_page=False)
        logout(page)

        browser.close()


def _embed_images_in_index() -> None:
    text = INDEX_HTML.read_text(encoding="utf-8")
    orig = text

    block1 = """          <!-- Production capture (optional): save PNG as docs/handbook/images/01-leadership-dashboard.png and uncomment:
          <img class="product-fig__shot" src="images/01-leadership-dashboard.png" alt="Mastex SchoolOS — leadership dashboard with sidebar navigation and metric cards." width="1200" height="675" decoding="async" /> -->"""
    repl1 = """          <img class="product-fig__shot" src="images/01-leadership-dashboard.png" alt="Mastex SchoolOS — leadership dashboard with sidebar navigation and metric cards." width="1200" height="675" decoding="async" />"""
    if (IMAGES_DIR / "01-leadership-dashboard.png").exists() and block1 in text:
        text = text.replace(block1, repl1, 1)

    simple = [
        (
            "02-school-fees.png",
            """          <!-- <img class="product-fig__shot" src="images/02-school-fees.png" alt="Mastex SchoolOS school fees list with balances." width="1200" height="675" decoding="async" /> -->""",
            """          <img class="product-fig__shot" src="images/02-school-fees.png" alt="Mastex SchoolOS school fees list with balances." width="1200" height="675" decoding="async" />""",
        ),
        (
            "03-parent-fees.png",
            """          <!-- <img class="product-fig__shot" src="images/03-parent-fees.png" alt="Mastex SchoolOS parent school fees and Paystack payment." width="1200" height="675" decoding="async" /> -->""",
            """          <img class="product-fig__shot" src="images/03-parent-fees.png" alt="Mastex SchoolOS parent school fees and Paystack payment." width="1200" height="675" decoding="async" />""",
        ),
        (
            "04-sign-in.png",
            """          <!-- <img class="product-fig__shot" src="images/04-sign-in.png" alt="Mastex SchoolOS sign in page." width="1200" height="675" decoding="async" /> -->""",
            """          <img class="product-fig__shot" src="images/04-sign-in.png" alt="Mastex SchoolOS sign in page." width="1200" height="675" decoding="async" />""",
        ),
        (
            "05-notifications.png",
            """          <!-- <img class="product-fig__shot" src="images/05-notifications.png" alt="Mastex SchoolOS notification bell and inbox preview." width="1200" height="675" decoding="async" /> -->""",
            """          <img class="product-fig__shot" src="images/05-notifications.png" alt="Mastex SchoolOS notification bell and inbox preview." width="1200" height="675" decoding="async" />""",
        ),
    ]
    for fname, commented, active in simple:
        if (IMAGES_DIR / fname).exists() and commented in text:
            text = text.replace(commented, active, 1)

    if text != orig:
        INDEX_HTML.write_text(text, encoding="utf-8")


class Command(BaseCommand):
    help = (
        "Capture handbook PNGs via Playwright using a temp SQLite DB; optionally embed into index.html."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-embed",
            action="store_true",
            help="Write PNGs only; do not modify docs/handbook/index.html.",
        )
        parser.add_argument(
            "--password",
            default=DEFAULT_PASSWORD,
            help="Demo user password (must match handbook_seed_demo).",
        )

    def handle(self, *args, **options):
        if not MANAGE_PY.is_file():
            raise CommandError(f"manage.py not found at {MANAGE_PY}")

        fd, db_path = tempfile.mkstemp(suffix=".sqlite3", prefix="handbook_capture_")
        os.close(fd)
        db_file = Path(db_path)
        db_url = f"sqlite:///{db_file.as_posix()}"
        port = _free_port()
        host = "127.0.0.1"

        env = os.environ.copy()
        env.pop("REDIS_URL", None)
        env["DATABASE_URL"] = db_url
        env["DJANGO_SETTINGS_MODULE"] = "schoolms.settings"
        env["DEBUG"] = "1"
        env.setdefault("SECRET_KEY", "handbook-capture-ephemeral-key-not-for-production")
        env.setdefault("LOG_LEVEL", "WARNING")

        try:
            subprocess.run(
                [sys.executable, str(MANAGE_PY), "migrate", "--noinput"],
                cwd=str(REPO_ROOT),
                env=env,
                check=True,
            )
            subprocess.run(
                [sys.executable, str(MANAGE_PY), "handbook_seed_demo", "--force", "--password", options["password"]],
                cwd=str(REPO_ROOT),
                env=env,
                check=True,
            )

            proc = subprocess.Popen(
                [
                    sys.executable,
                    str(MANAGE_PY),
                    "runserver",
                    f"{host}:{port}",
                    "--noreload",
                ],
                cwd=str(REPO_ROOT),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            time.sleep(2.5)
            if proc.poll() is not None:
                err = (proc.stderr.read() or "") if proc.stderr else ""
                raise CommandError(f"runserver exited early:\n{err}")

            base = f"http://{host}:{port}"
            try:
                _capture_with_playwright(base, options["password"])
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()

            self.stdout.write(self.style.SUCCESS(f"Wrote PNGs under {IMAGES_DIR}"))

            if not options["no_embed"]:
                _embed_images_in_index()
                self.stdout.write(self.style.SUCCESS(f"Embedded shots in {INDEX_HTML} (where PNGs exist)."))

        finally:
            db_file.unlink(missing_ok=True)
