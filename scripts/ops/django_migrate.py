#!/usr/bin/env python3
# =============================================================================
# MANUAL EC2 STEPS (Bash) — same as:  python scripts/ops/django_migrate.py  [args...]
#
#   cd /srv/django-app
#   source venv/bin/activate
#   set -a
#   source /etc/django/backend.env
#   set +a
#   python manage.py migrate            # add e.g. --plan appname after migrate
#
# Env file + manage.py are wired in env_support.py. Adjust cd if needed.
# =============================================================================

"""Run ``manage.py migrate``. Extra CLI args are forwarded to migrate."""

import sys
from pathlib import Path

_OPS = Path(__file__).resolve().parent
sys.path.insert(0, str(_OPS))

from env_support import run_manage  # noqa: E402


if __name__ == "__main__":
    extra = sys.argv[1:]
    run_manage(["migrate", *extra])
