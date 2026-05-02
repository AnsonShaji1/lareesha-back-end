#!/usr/bin/env python3
# =============================================================================
# MANUAL EC2 STEPS (Bash) — same as:  python scripts/ops/deploy_web.py
#
#   cd /srv/django-app
#   source venv/bin/activate
#   set -a
#   source /etc/django/backend.env
#   set +a
#   python manage.py migrate
#   python manage.py collectstatic --noinput
#   sudo systemctl restart gunicorn
#
# The Python script runs those three operational steps using env_support.py
# (env) + sudo for gunicorn. It does NOT run the "cd/source/set" shell lines;
# those are what you would type manually.
# =============================================================================

"""migrate → collectstatic --noinput → sudo restart gunicorn."""

import sys
from pathlib import Path

_OPS = Path(__file__).resolve().parent
sys.path.insert(0, str(_OPS))

from env_support import django_run, sudo_run  # noqa: E402


def main() -> None:
    steps = [
        ("migrate", ["migrate"]),
        ("collectstatic", ["collectstatic", "--noinput"]),
    ]
    for name, args in steps:
        code = django_run(args)
        if code != 0:
            print(f"deploy_web: step {name} failed (exit {code})", file=sys.stderr)
            sys.exit(code)
    code = sudo_run(["systemctl", "restart", "gunicorn"])
    if code != 0:
        print(f"deploy_web: gunicorn restart failed (exit {code})", file=sys.stderr)
    sys.exit(code)


if __name__ == "__main__":
    main()
