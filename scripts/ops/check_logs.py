#!/usr/bin/env python3
# =============================================================================
# MANUAL EC2 EXAMPLES (Bash) — Django errors usually appear under Gunicorn
#
#   sudo journalctl -u gunicorn -n 200 --no-pager
#   sudo journalctl -u gunicorn -n 200 -f                    # follow live
#
# Nginx files:
#   sudo tail -n 200 /var/log/nginx/error.log
#   sudo tail -f /var/log/nginx/error.log
#
# This Python file only wraps those commands; read argparse below for targets.
# =============================================================================
"""
Show or follow common server logs on EC2 (requires sudo).

Django request/runtime errors with Gunicorn → systemd journal for the gunicorn unit.

Examples:
  python scripts/ops/check_logs.py gunicorn
  python scripts/ops/check_logs.py gunicorn -f
  python scripts/ops/check_logs.py gunicorn -n 500 --since today
  python scripts/ops/check_logs.py nginx-error -f
  python scripts/ops/check_logs.py postgresql --unit postgresql@16-main
"""

from __future__ import annotations

import argparse
import subprocess
import sys


def _journalctl(unit: str, lines: int, follow: bool, since: str | None) -> list[str]:
    cmd = ["sudo", "journalctl", "-u", unit]
    if since:
        cmd.extend(["--since", since])
    if follow:
        cmd.extend(["-n", str(lines), "-f"])
    else:
        cmd.extend(["-n", str(lines), "--no-pager"])
    return cmd


def _tail(path: str, lines: int, follow: bool) -> list[str]:
    cmd = ["sudo", "tail", "-n", str(lines)]
    if follow:
        cmd.append("-f")
    cmd.append(path)
    return cmd


def main() -> None:
    parser = argparse.ArgumentParser(
        description="View Gunicorn (Django), Nginx, or PostgreSQL logs."
    )
    parser.add_argument(
        "target",
        choices=("gunicorn", "nginx-error", "nginx-access", "postgresql"),
        help="gunicorn = Django app errors via journald; nginx-* = file logs",
    )
    parser.add_argument(
        "-f",
        "--follow",
        action="store_true",
        help="Stream new lines (Ctrl+C to stop)",
    )
    parser.add_argument(
        "-n",
        "--lines",
        type=int,
        default=200,
        metavar="N",
        help="Initial line count (default: 200)",
    )
    parser.add_argument(
        "--since",
        metavar="SPEC",
        help="journalctl only: e.g. today, -1h, '2024-01-01 00:00:00'",
    )
    parser.add_argument(
        "--unit",
        metavar="NAME",
        help="Override systemd unit for gunicorn or postgresql (e.g. postgresql@16-main)",
    )
    args = parser.parse_args()

    if args.target == "gunicorn":
        unit = args.unit or "gunicorn"
        cmd = _journalctl(unit, args.lines, args.follow, args.since)
    elif args.target == "nginx-error":
        if args.since or args.unit:
            print(
                "check_logs: --since and --unit apply only to journalctl targets",
                file=sys.stderr,
            )
        cmd = _tail("/var/log/nginx/error.log", args.lines, args.follow)
    elif args.target == "nginx-access":
        if args.since or args.unit:
            print(
                "check_logs: --since and --unit apply only to journalctl targets",
                file=sys.stderr,
            )
        cmd = _tail("/var/log/nginx/access.log", args.lines, args.follow)
    else:
        unit = args.unit or "postgresql"
        cmd = _journalctl(unit, args.lines, args.follow, args.since)

    sys.exit(subprocess.run(cmd).returncode)


if __name__ == "__main__":
    main()
