"""Constants for the DTE Multi-Meter Usage integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "dte_multi_meter"
PLATFORMS = ["sensor"]

DEFAULT_NAME = "DTE Multi-Meter"
DEFAULT_SCAN_INTERVAL = timedelta(hours=24)

STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = f"{DOMAIN}_cumulative"
