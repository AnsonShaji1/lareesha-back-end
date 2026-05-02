#!/usr/bin/env python3
# =============================================================================
# MANUAL EC2 STEPS (copy-paste in Bash) — same as running this Python file
#
#   cd /srv/django-app
#   source venv/bin/activate
#   set -a
#   source /etc/django/backend.env
#   set +a
#   python manage.py check
#
# Python does NOT run those lines for you. They are here so you see the flow.
# This file automates: load /etc/django/backend.env + run manage.py check
# (see env_support.py). Use back-end/ instead of django-app if manage.py is there.
#
# Other env file:
#   BACKEND_ENV_FILE=/path/to/.env python scripts/ops/django_check.py
# =============================================================================

"""Run ``manage.py check`` (env file loaded in env_support.py; read # block above)."""

import sys
from pathlib import Path

_OPS = Path(__file__).resolve().parent
sys.path.insert(0, str(_OPS))

from env_support import run_manage  # noqa: E402


if __name__ == "__main__":
    extra = sys.argv[1:]
    run_manage(["check", *extra])
