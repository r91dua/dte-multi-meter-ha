"""External statistics importer for DTE Multi-Meter Usage."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from typing import Any

from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .api import DTEInterval, DTEMeter, DTEParsedData
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

try:
    from homeassistant.components.recorder.models import StatisticMeanType
except ImportError:  # pragma: no cover - older Home Assistant compatibility
    StatisticMeanType = None  # type: ignore[assignment]


@dataclass(slots=True)
class StatisticsImportResult:
    """Summary of one statistics import run."""

    imported_rows: int
    updated_statistic_ids: list[str]


async def async_import_dte_external_statistics(
    hass: HomeAssistant,
    parsed: DTEParsedData,
    stored_statistics: dict[str, Any],
) -> StatisticsImportResult:
    """Import DTE interval readings into Home Assistant long-term statistics.

    This imports only intervals newer than the last interval already imported for
    each meter/statistic. That keeps the external statistic monotonic even though
    the DTE export is a rolling history window.
    """
    imported_rows = 0
    updated_statistic_ids: list[str] = []

    for meter_id, meter in parsed.meters.items():
        rows_imported, statistic_id = _import_meter_statistics(
            hass=hass,
            meter_key=meter_id,
            service=meter.service,
            name=meter.name,
            unit=meter.unit,
            intervals=meter.intervals,
            stored_statistics=stored_statistics,
        )
        imported_rows += rows_imported
        if rows_imported:
            updated_statistic_ids.append(statistic_id)

    # Also create an external imported aggregate for all electric meters, matching
    # the live "DTE Electric Total" sensor. Use this OR the individual imported
    # electric meters in Energy Dashboard, not both.
    electric_meters = [
        meter for meter in parsed.meters.values() if meter.service == "electric"
    ]
    if len(electric_meters) > 1:
        aggregate_intervals = _aggregate_electric_intervals(electric_meters)
        rows_imported, statistic_id = _import_meter_statistics(
            hass=hass,
            meter_key="__electric_total__",
            service="electric",
            name="Electric Total",
            unit="kWh",
            intervals=aggregate_intervals,
            stored_statistics=stored_statistics,
        )
        imported_rows += rows_imported
        if rows_imported:
            updated_statistic_ids.append(statistic_id)

    return StatisticsImportResult(
        imported_rows=imported_rows,
        updated_statistic_ids=updated_statistic_ids,
    )


def _import_meter_statistics(
    *,
    hass: HomeAssistant,
    meter_key: str,
    service: str,
    name: str,
    unit: str,
    intervals: list[DTEInterval],
    stored_statistics: dict[str, Any],
) -> tuple[int, str]:
    """Import statistics for one real or synthetic meter."""
    intervals = sorted(intervals, key=lambda row: row.start)
    if not intervals:
        return 0, ""

    object_id = _object_id_for_meter(service, name)
    statistic_id = f"{DOMAIN}:{object_id}"
    metadata = _metadata_for_meter(statistic_id, service, name, unit)

    stored = stored_statistics.setdefault(
        meter_key,
        {
            "statistic_id": statistic_id,
            "latest_end": 0,
            "cumulative_sum": 0.0,
        },
    )

    # Once established, keep the external statistic_id stable.
    statistic_id = stored.get("statistic_id", statistic_id)
    metadata["statistic_id"] = statistic_id

    previous_latest_end = int(stored.get("latest_end", 0) or 0)
    cumulative_sum = float(stored.get("cumulative_sum", 0.0) or 0.0)

    rows = []
    for interval in intervals:
        if interval.end <= previous_latest_end:
            continue

        cumulative_sum = round(cumulative_sum + interval.usage, 6)
        rows.append(
            {
                "start": _interval_start_as_utc_hour(interval),
                "state": cumulative_sum,
                "sum": cumulative_sum,
            }
        )

    if not rows:
        return 0, statistic_id

    try:
        async_add_external_statistics(hass, metadata, rows)
    except HomeAssistantError:
        _LOGGER.exception("Failed to import DTE statistics for %s", statistic_id)
        return 0, statistic_id

    latest_imported = max(
        interval.end for interval in intervals if interval.end > previous_latest_end
    )
    stored["latest_end"] = latest_imported
    stored["cumulative_sum"] = cumulative_sum
    stored["statistic_id"] = statistic_id

    return len(rows), statistic_id


def _aggregate_electric_intervals(electric_meters: list[DTEMeter]) -> list[DTEInterval]:
    """Aggregate same-timestamp electric meter intervals into one total interval."""
    usage_by_key: dict[tuple[int, int], float] = defaultdict(float)

    for meter in electric_meters:
        for interval in meter.intervals:
            usage_by_key[(interval.start, interval.duration)] += interval.usage

    return [
        DTEInterval(start=start, duration=duration, usage=round(usage, 6))
        for (start, duration), usage in sorted(usage_by_key.items())
    ]


def _metadata_for_meter(
    statistic_id: str,
    service: str,
    name: str,
    unit: str,
) -> dict[str, Any]:
    """Build recorder statistics metadata for one DTE meter."""
    metadata: dict[str, Any] = {
        "has_sum": True,
        "name": f"DTE {name} Imported",
        "source": DOMAIN,
        "statistic_id": statistic_id,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR if service == "electric" else "CCF",
    }

    if StatisticMeanType is None:
        # Older Home Assistant versions used has_mean. Kept for compatibility.
        metadata["has_mean"] = False
    else:
        metadata["mean_type"] = StatisticMeanType.NONE
        # Home Assistant 2025.11+/2026.11+ expects unit_class in imported
        # statistics metadata. kWh maps to energy. CCF is a gas volume unit.
        metadata["unit_class"] = "energy" if service == "electric" else "volume"

    return metadata


def _object_id_for_meter(service: str, name: str) -> str:
    """Return a stable external statistics object ID."""
    normalized = (
        name.lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("__", "_")
    )
    return f"{service}_{normalized}"


def _interval_start_as_utc_hour(interval: DTEInterval) -> datetime:
    """Return interval start as a timezone-aware UTC top-of-hour datetime."""
    start = datetime.fromtimestamp(interval.start, UTC)
    return start.replace(minute=0, second=0, microsecond=0)
