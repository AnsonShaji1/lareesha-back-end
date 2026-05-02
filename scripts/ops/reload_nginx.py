#!/usr/bin/env python3
# =============================================================================
# MANUAL EC2 EQUIVALENT (Bash)
#
#   sudo nginx -t
#   sudo systemctl reload nginx
#
# Validates config then reloads Nginx without a full stop/start.
# =============================================================================

"""sudo nginx -t && sudo systemctl reload nginx."""

import sys
from pathlib import Path

_OPS = Path(__file__).resolve().parent
sys.path.insert(0, str(_OPS))

from env_support import sudo_run  # noqa: E402


def main() -> None:
    if sudo_run(["nginx", "-t"]) != 0:
        sys.exit(1)
    sys.exit(sudo_run(["systemctl", "reload", "nginx"]))


if __name__ == "__main__":
    main()
