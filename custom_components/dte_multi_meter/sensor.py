"""Sensor platform for DTE Multi-Meter Usage."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DTEMultiMeterCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DTE Multi-Meter sensors."""
    coordinator: DTEMultiMeterCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []
    meters = coordinator.data.get("meters", {})

    for meter_id in meters:
        entities.append(DTEMeterSensor(coordinator, meter_id))

    electric_meter_ids = [
        meter_id
        for meter_id, meter in meters.items()
        if meter.get("service") == "electric"
    ]
    if len(electric_meter_ids) > 1:
        entities.append(DTEElectricTotalSensor(coordinator, electric_meter_ids))

    async_add_entities(entities)


class DTEMeterSensor(CoordinatorEntity[DTEMultiMeterCoordinator], SensorEntity):
    """Sensor for one DTE meter / usage point."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_should_poll = False

    def __init__(self, coordinator: DTEMultiMeterCoordinator, meter_id: str) -> None:
        """Initialize the meter sensor."""
        super().__init__(coordinator)
        self.meter_id = meter_id
        meter = coordinator.data["meters"][meter_id]
        self._attr_name = f"DTE {meter['name']}"
        self._attr_unique_id = f"{DOMAIN}_{meter_id}_total"

        if meter["service"] == "electric":
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_suggested_display_precision = 3
        else:
            self._attr_device_class = SensorDeviceClass.GAS
            self._attr_native_unit_of_measurement = "CCF"
            self._attr_suggested_display_precision = 3

    @property
    def native_value(self) -> float | None:
        """Return the cumulative usage."""
        meter = self.coordinator.data.get("meters", {}).get(self.meter_id)
        if meter is None:
            return None
        return meter.get("total")

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        meter = self.coordinator.data["meters"][self.meter_id]
        return {
            "identifiers": {(DOMAIN, self.meter_id)},
            "name": f"DTE {meter['name']}",
            "manufacturer": "DTE Energy",
            "model": "Green Button UsagePoint",
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional debugging attributes."""
        meter = self.coordinator.data.get("meters", {}).get(self.meter_id, {})
        statistics_import = self.coordinator.data.get("statistics_import", {})
        stored_statistics = {}
        if self.coordinator._stored is not None:  # pylint: disable=protected-access
            stored_statistics = (
                self.coordinator._stored.get("statistics", {}).get(self.meter_id, {})
            )

        return {
            "usage_point_id": self.meter_id,
            "service": meter.get("service"),
            "latest_interval_usage": meter.get("latest_interval_usage"),
            "latest_interval_start": meter.get("latest_interval_start"),
            "latest_interval_end": meter.get("latest_interval_end"),
            "interval_count": meter.get("interval_count"),
            "history_total_from_current_dte_feed": meter.get("history_total"),
            "source_updated": meter.get("source_updated"),
            "external_statistic_id": stored_statistics.get("statistic_id"),
            "external_statistics_latest_end": stored_statistics.get("latest_end"),
            "external_statistics_cumulative_sum": stored_statistics.get("cumulative_sum"),
            "statistics_imported_rows_last_refresh": statistics_import.get("imported_rows"),
            "statistics_import_last_error": statistics_import.get("last_error"),
        }


class DTEElectricTotalSensor(CoordinatorEntity[DTEMultiMeterCoordinator], SensorEntity):
    """Aggregate total electric usage sensor across all DTE electric meters."""

    _attr_name = "DTE Electric Total"
    _attr_unique_id = f"{DOMAIN}_electric_total"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 3
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: DTEMultiMeterCoordinator,
        electric_meter_ids: list[str],
    ) -> None:
        """Initialize the aggregate electric sensor."""
        super().__init__(coordinator)
        self.electric_meter_ids = electric_meter_ids

    @property
    def native_value(self) -> float | None:
        """Return the cumulative total across electric meters."""
        meters = self.coordinator.data.get("meters", {})
        values = []
        for meter_id in self.electric_meter_ids:
            meter = meters.get(meter_id)
            if meter is None or meter.get("total") is None:
                continue
            values.append(float(meter["total"]))
        if not values:
            return None
        return round(sum(values), 6)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return child meter attributes."""
        return {
            "source_meter_entity_count": len(self.electric_meter_ids),
            "source_usage_point_ids": self.electric_meter_ids,
            "source_updated": self.coordinator.data.get("updated"),
        }
