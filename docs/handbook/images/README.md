# Handbook screenshots (optional)

This folder holds **real product PNGs** for the printable handbook (`../index.html`). Until you add files, the handbook shows **built-in CSS mockups** that match Mastex SchoolOS (dark theme, green accents).

## Recommended captures

| File | What to screenshot |
|------|-------------------|
| `01-leadership-dashboard.png` | School admin dashboard with sidebar + metrics |
| `02-school-fees.png` | Finance **School fees** list (blur names if needed) |
| `03-parent-fees.png` | Parent **School fees** view with balance / Pay button |
| `04-sign-in.png` | Login page |
| `05-notifications.png` | Header with bell + notification list or `/notifications/` |

## How to capture

### Automatic (from this repo)

See [../README.md](../README.md) — run `python manage.py capture_handbook_screenshots` after installing Playwright. No manual browser steps.

### Manual

1. Use **Chrome** or **Edge**, zoom **100%**.
2. Resize the window to about **1280px** or **1440px** wide (or use device toolbar).
3. **PNG** format, full width of the content area (not the whole monitor unless cropped).
4. Avoid showing real minors’ full names in marketing PDFs — use test accounts or blur.

## Enable in the handbook

1. Save PNGs in this folder with the names above.
2. Open `../index.html` in an editor.
3. For each figure, **uncomment** the `<img class="product-fig__shot" … />` line that matches the filename.
4. Refresh the page in the browser; the image replaces the mockup automatically (`:has()` selector — use a current browser).

**Relative paths:** Open `index.html` via a local server (e.g. `python -m http.server` from `docs/handbook`) so `images/…` resolves correctly; or open the file directly — most browsers still load sibling `images/` paths.

## Cover thumbnails

Optional: replace the small **cover** device mockups by editing the cover section in `index.html` — or leave them as stylised previews.
