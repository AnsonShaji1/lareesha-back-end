#!/usr/bin/env python3
# =============================================================================
# MANUAL EC2 STEPS (Bash) — same as:  python scripts/ops/django_collectstatic.py
#
#   cd /srv/django-app
#   source venv/bin/activate
#   set -a
#   source /etc/django/backend.env
#   set +a
#   python manage.py collectstatic --noinput
#
# This script defaults to --noinput when you pass no args. Env: env_support.py
# =============================================================================

"""Run ``manage.py collectstatic`` (default ``--noinput`` if no args)."""

import sys
from pathlib import Path

_OPS = Path(__file__).resolve().parent
sys.path.insert(0, str(_OPS))

from env_support import run_manage  # noqa: E402


if __name__ == "__main__":
    extra = sys.argv[1:] if sys.argv[1:] else ["--noinput"]
    run_manage(["collectstatic", *extra])
