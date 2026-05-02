# Updating environment variables on EC2 (`/etc/django/backend.env`)

Gunicorn reads variables from systemd’s **`EnvironmentFile=/etc/django/backend.env`** when the **process starts**. Editing the file alone does **not** change already-running workers; you **must restart Gunicorn** after changes.

---

## Recommended order

| Step | What to run |
|------|--------------|
| 1 | Edit the env file |
| 2 | **Verify** Django can load settings with the **new** values (optional but recommended) |
| 3 | **Restart Gunicorn** so the live app picks up the file |

Restarting nginx is **not** required for Django env-only changes unless you changed nginx config.

---

## 1. Edit the file

```bash
sudo nano /etc/django/backend.env
```

Save and exit (`Ctrl+O`, `Ctrl+X` in nano).

---

## 2. Verify configuration (pick one approach)

### Option A — Ops script (simplest)

From the Django project root (`manage.py` and `venv/` live here):

```bash
cd /srv/django-app
source venv/bin/activate
python scripts/ops/django_check.py
```

This script merges **`/etc/django/backend.env`** into the subprocess environment (same idea as systemd’s `EnvironmentFile`), so you do **not** need `set -a` / `source …` manually.

### Option B — Plain `manage.py` (manual shell load)

If you prefer raw `manage.py`, you **must** load the **same file** Gunicorn uses; otherwise Django may fall back only on `/srv/django-app/.env` from `python-dotenv` (see `override=False` in settings).

```bash
cd /srv/django-app
source venv/bin/activate
set -a
source /etc/django/backend.env
set +a
python manage.py check
```

**Common mistake:** running `manage.py check` **without** `source /etc/django/backend.env`. That checks your **terminal** env and project `.env`, not necessarily production `backend.env`.

---

## 3. Apply changes to the running app

```bash
sudo systemctl restart gunicorn
```

If systemd warns that a **unit file** changed on disk (not because of `backend.env`), reload unit definitions:

```bash
sudo systemctl daemon-reload
sudo systemctl restart gunicorn
```

`daemon-reload` is **not** normally required when you only edited `backend.env`.

---

## Quick copy-paste (edit → verify → restart)

Replace the editor step with your preferred tool if needed.

```bash
sudo nano /etc/django/backend.env

cd /srv/django-app
source venv/bin/activate
python scripts/ops/django_check.py

sudo systemctl restart gunicorn
```

---

## Check Gunicorn if something breaks

```bash
sudo systemctl status gunicorn
python scripts/ops/check_logs.py gunicorn -n 100
```

---

## Permissions (reference)

Keeping `backend.env` root-owned and unreadable by world-wide users is typical, e.g.:

```bash
sudo chown root:ubuntu /etc/django/backend.env
sudo chmod 640 /etc/django/backend.env
```

Adjust group/user if your setup differs.
