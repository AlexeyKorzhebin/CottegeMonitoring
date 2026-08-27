"""Operator CLI for the Nord Ops catalog.

Usage (in Docker image)::

    docker run --rm --entrypoint cottage-ops cottage-monitoring:latest catalog
    docker run --rm --entrypoint cottage-ops cottage-monitoring:latest catalog --json
"""

from __future__ import annotations

import argparse
import json

from cottage_monitoring.ops.catalog import load_catalog
from cottage_monitoring.ops.registry import op_names


def catalog_names() -> tuple[str, ...]:
    load_catalog()
    return op_names()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CottageMonitoring Ops operator CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    cat = sub.add_parser("catalog", help="Print Ops names from the registry")
    cat.add_argument("--json", action="store_true", help="Print names as a JSON array")
    args = parser.parse_args(argv)

    if args.command == "catalog":
        names = catalog_names()
        if args.json:
            print(json.dumps(list(names)))
        else:
            print("\n".join(names))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
