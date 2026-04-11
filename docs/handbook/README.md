# Mastex SchoolOS — Printable Handbook

This folder contains **`index.html`**, a self-contained, professionally styled handbook for **schools** (training, parent orientation, and procurement). It intentionally does **not** describe internal platform-operator tools. **Mastex Technologies** — [mastexedu.online](https://mastexedu.online) · mastex.digital.world@gmail.com · WhatsApp +233 544 789 716 — is the product vendor for demos, licensing, and platform support.

## Generate a PDF

1. Open **`index.html`** in **Google Chrome** or **Microsoft Edge** (recommended).
2. Press **Ctrl+P** (Windows) or **Cmd+P** (Mac).
3. Choose **Save as PDF** (or your printer).
4. Set **Paper size** to **A4** (or Letter for US).
5. Enable **Background graphics** if you want the cover and accent colors to print as designed.
6. In **More settings**, optional: enable the browser’s **Headers and footers** for automatic page numbers and date.

## Product screenshots (optional)

The handbook includes **five full interface figures** plus **cover thumbnails** — stylised mockups that mirror the real Mastex SchoolOS UI.

### Automated capture (recommended)

From the **repository root** (same folder as `manage.py`):

```bash
pip install -r docs/handbook/requirements-capture.txt
python -m playwright install chromium
python manage.py capture_handbook_screenshots
```

This uses a **temporary SQLite database** (your real `DATABASE_URL` is not touched), migrates, seeds demo users, starts `runserver` on a random port, saves **`docs/handbook/images/01-…05-….png`**, and **uncomments** the matching `<img>` lines in `index.html`. Use **`--no-embed`** if you only want the PNG files. Demo logins: `handbook_admin` / `handbook_parent` (password `HandbookDemo2026!` in the seed command — override with `--password` on both commands if needed).

### Manual PNGs

To add **your own** production PNGs instead, see [images/README.md](images/README.md) and uncomment the `<img>` lines in `index.html`.

## Customise for your school

Edit **`index.html`** and replace the placeholder lines in the cover block:

- Your school name (cover bottom)
- Edition date
- Optional: add real screenshots per `images/README.md`

## Also available

- Markdown user guide: [../MASTEX_USER_GUIDE.md](../MASTEX_USER_GUIDE.md)
