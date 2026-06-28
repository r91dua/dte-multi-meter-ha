"""Coordinator for DTE Multi-Meter Usage."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientSession

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DTEDataError, fetch_dte_xml, parse_dte_green_button_xml
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, STORAGE_KEY_PREFIX, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


class DTEMultiMeterCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch and normalize DTE usage data for all meters in one URL."""

    def __init__(
        self,
        hass: HomeAssistant,
        url: str,
        entry_id: str,
        name: str,
        session: ClientSession,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=DEFAULT_SCAN_INTERVAL,
            always_update=False,
        )
        self.url = url
        self.entry_id = entry_id
        self.session = session
        self.store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY_PREFIX}_{entry_id}")
        self._stored: dict[str, Any] | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the DTE URL and return meter states."""
        try:
            if self._stored is None:
                self._stored = await self.store.async_load() or {"meters": {}}

            xml_text = await fetch_dte_xml(self.session, self.url)
            parsed = parse_dte_green_button_xml(xml_text)

            stored_meters: dict[str, Any] = self._stored.setdefault("meters", {})
            changed = False
            meters: dict[str, dict[str, Any]] = {}

            for meter_id, meter in parsed.meters.items():
                intervals = sorted(meter.intervals, key=lambda row: row.start)
                if not intervals:
                    continue

                latest = intervals[-1]
                latest_end = latest.end
                history_total = round(sum(row.usage for row in intervals), 6)

                stored = stored_meters.get(meter_id)
                if stored is None:
                    # First install: seed with the full history DTE returns.
                    total = history_total
                    stored_meters[meter_id] = {
                        "total": total,
                        "latest_end": latest_end,
                    }
                    changed = True
                else:
                    total = float(stored.get("total", 0.0))
                    previous_latest_end = int(stored.get("latest_end", 0))
                    if latest_end > previous_latest_end:
                        new_usage = sum(
                            row.usage
                            for row in intervals
                            if row.end > previous_latest_end
                        )
                        total = round(total + new_usage, 6)
                        stored["total"] = total
                        stored["latest_end"] = latest_end
                        changed = True

                meters[meter_id] = {
                    "meter_id": meter_id,
                    "name": meter.name,
                    "service": meter.service,
                    "unit": meter.unit,
                    "total": round(total, 6),
                    "history_total": history_total,
                    "interval_count": len(intervals),
                    "latest_interval_usage": round(latest.usage, 6),
                    "latest_interval_start": latest.start,
                    "latest_interval_end": latest.end,
                    "source_updated": parsed.updated,
                }

            if changed:
                await self.store.async_save(self._stored)

            return {
                "meters": meters,
                "updated": parsed.updated,
            }

        except DTEDataError as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Unexpected error fetching DTE data: {err}") from err
