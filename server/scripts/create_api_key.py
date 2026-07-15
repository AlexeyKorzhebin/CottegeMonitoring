#!/usr/bin/env python3
"""Backward-compatible wrapper — prefer console script `cottage-create-api-key`."""

from cottage_monitoring.cli.create_api_key import main

if __name__ == "__main__":
    raise SystemExit(main())
