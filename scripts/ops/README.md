# `scripts/ops` — server helper commands

Small Python wrappers for common **EC2 / production** tasks. Run them with the **same Python as your Django app** (recommended: activate the project `venv` first).

**How to read these scripts:** Every `*.py` here starts with a **`# ===...===` comment block** that shows the **manual Bash you would type** (e.g. `cd`, `source venv`, `set -a`, `source /etc/django/backend.env`, `python manage.py …`). Python **does not run** those comment lines; they are only documentation in the file. The real behavior is in **`env_support.py`** (load env file + run `manage.py`) or `sudo`/`journalctl` wrappers as noted in each file.

All Django-related scripts merge `/etc/django/backend.env` into the environment unless you override with `BACKEND_ENV_FILE`:

```bash
export BACKEND_ENV_FILE=/path/to/.env   # optional; default is production path below
```

**Assumed paths on EC2 (adjust if yours differ):**

- App root containing `manage.py`: e.g. `/srv/django-app/back-end` (this repo layout) or `/srv/django-app` if you deploy only that tree.
- Python venv: e.g. `/srv/django-app/venv` or `/srv/django-app/back-end/venv`.

**Go to the directory that contains `manage.py`** (often `/srv/django-app` if the repo root is only the Django app, or `.../back-end` in this monorepo layout):

```bash
cd /srv/django-app                       # <-- change if manage.py lives in a subfolder, e.g. back-end/
source venv/bin/activate
```

Before `manage.py` (check, migrate, shell, …), load the same secrets/settings Gunicorn uses from **`EnvironmentFile=/etc/django/backend.env`**. Shell one-liners:

```bash
set -a                                   # export every VAR=value that follows
source /etc/django/backend.env
set +a                                   # stop auto-export

python manage.py check
```

- **`set -a`**: bash marks each variable assignment as exported so **child processes** (like `python`) see them.
- **`source`** (same as `.`): runs the file in the **current** shell so variables persist.
- **`set +a`**: turns that behavior off afterward.

Equivalent without typing that block: **`python scripts/ops/django_check.py`** (same default env file unless you set `BACKEND_ENV_FILE`). Use whichever you prefer.

For other commands after loading env the same way:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py shell
```

---

## 1. Typical order after **first clone** / new server

These are Bash steps (venv, DB, systemd) — the ops scripts complement them rather than replacing OS setup.

| Step | What to run |
|------|----------------|
| 1 | Install system packages, create venv, `pip install -r requirements.txt` |
| 2 | Create `/etc/django/backend.env` and Postgres DB/user |
| 3 | **Check:** `(cd …, venv, set -a, source …, set +a)` → `python manage.py check`, **or** `python scripts/ops/django_check.py` |
| 4 | `python scripts/ops/django_migrate.py` |
| 5 | `python scripts/ops/django_collectstatic.py` (uses `--noinput` when no extra args) |
| 6 | `python scripts/ops/django_createsuperuser.py` (once, interactive) |
| 7 | Install/configure **gunicorn** + **nginx** systemd units on the server (see your deployment notes) |

---

## 2. Typical order for a **routine deploy** (code + migrations + static)

| Order | Command | Purpose |
|------|---------|--------|
| 1 | `git pull` | Update code |
| 2 | `pip install -r requirements.txt` | If dependencies changed |
| 3 | `python scripts/ops/deploy_web.py` | `migrate` → `collectstatic --noinput` → `sudo systemctl restart gunicorn` |

Bash-only steps (pull **`master`**, optional stash/clean, **`deploy_web.py`**): **`EC2_GIT_PULL_MASTER_STEPS.md`**.

Or run the pieces yourself (same logical order):

1. `python scripts/ops/django_migrate.py`
2. `python scripts/ops/django_collectstatic.py`
3. `python scripts/ops/restart_gunicorn.py`

---

## 3. Change **environment variables** (`backend.env`)

| Order | Command |
|------|---------|
| 1 | Edit `/etc/django/backend.env` (e.g. `sudo nano …`) |
| 2 | `python scripts/ops/restart_gunicorn.py` |

(Optional sanity check before restart.)

```bash
python scripts/ops/django_check.py
```

---

## 4. Change **Nginx** configuration

| Order | Command |
|------|---------|
| 1 | Edit site config under `/etc/nginx/…` |
| 2 | `python scripts/ops/reload_nginx.py` (runs `nginx -t` then `systemctl reload nginx`) |

---

## 5. **Reference**: each script

Run from directory that contains `scripts/ops/` (usually the same folder as `manage.py`).

| Script | Purpose | Example |
|--------|---------|---------|
| `env_support.py` | Shared helper (not meant to run alone) | — |
| `django_check.py` | `manage.py check` | `python scripts/ops/django_check.py` |
| `django_migrate.py` | `manage.py migrate` | `python scripts/ops/django_migrate.py` |
| | Forward extra args | `python scripts/ops/django_migrate.py --plan api` |
| `django_collectstatic.py` | `collectstatic` | `python scripts/ops/django_collectstatic.py` |
| | Defaults to `--noinput` if no args | `python scripts/ops/django_collectstatic.py` |
| `django_shell.py` | `manage.py shell` | `python scripts/ops/django_shell.py` |
| `django_createsuperuser.py` | `manage.py createsuperuser` | `python scripts/ops/django_createsuperuser.py` |
| `restart_gunicorn.py` | `sudo systemctl restart gunicorn` | `python scripts/ops/restart_gunicorn.py` |
| `reload_nginx.py` | `sudo nginx -t` + reload nginx | `python scripts/ops/reload_nginx.py` |
| `deploy_web.py` | Migrate + collectstatic + restart gunicorn | `python scripts/ops/deploy_web.py` |
| `check_logs.py` | Tail / journalctl wrappers | See below |

**Using non-default env file:**

```bash
BACKEND_ENV_FILE=/home/ubuntu/.secrets/backend.env python scripts/ops/django_check.py
```

---

## 6. **Logs** (`check_logs.py`)

Django/Python errors under Gunicorn usually appear under the **`gunicorn`** systemd unit.

```bash
# Last 200 lines
python scripts/ops/check_logs.py gunicorn

# Follow (live)
python scripts/ops/check_logs.py gunicorn -f

# More lines / time filter (journalctl)
python scripts/ops/check_logs.py gunicorn -n 500 --since today
```

Nginx:

```bash
python scripts/ops/check_logs.py nginx-error -f
python scripts/ops/check_logs.py nginx-access -n 400
```

PostgreSQL (unit name may vary, e.g. `postgresql@16-main`):

```bash
python scripts/ops/check_logs.py postgresql
python scripts/ops/check_logs.py postgresql --unit postgresql@16-main -f
```

Scripts that call `sudo` may prompt for a password unless you configure passwordless sudo for those commands.

---

## 7. **Without** activating venv

```bash
/srv/django-app/venv/bin/python /srv/django-app/back-end/scripts/ops/deploy_web.py
```

(Adjust both paths to match your server.)

---

## 8. **Troubleshooting**

| Issue | Where to look |
|------|----------------|
| Traceback / 500 | `python scripts/ops/check_logs.py gunicorn -f` |
| 502 / upstream | `check_logs.py nginx-error` + gunicorn status: `sudo systemctl status gunicorn` |
| Env not applied | Restart gunicorn after editing `/etc/django/backend.env` |
| `manage.py` not found | Run from directory that contains `manage.py`; same relative layout as this repo (`back-end/scripts/ops/`). |
