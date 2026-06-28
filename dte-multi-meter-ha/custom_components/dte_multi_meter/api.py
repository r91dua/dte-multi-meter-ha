"""DTE Green Button XML parsing helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import xml.etree.ElementTree as ET

from aiohttp import ClientError, ClientSession

ATOM_NS = "http://www.w3.org/2005/Atom"
ESPI_NS = "http://naesb.org/espi"

NS = {
    "atom": ATOM_NS,
    "espi": ESPI_NS,
}


class DTEDataError(Exception):
    """Raised when the DTE URL or XML cannot be parsed."""


@dataclass(slots=True)
class DTEInterval:
    """One DTE interval reading."""

    start: int
    duration: int
    usage: float

    @property
    def end(self) -> int:
        """Return the interval end epoch timestamp."""
        return self.start + self.duration


@dataclass(slots=True)
class DTEMeter:
    """One DTE usage point / meter."""

    meter_id: str
    name: str
    service: str
    unit: str
    intervals: list[DTEInterval] = field(default_factory=list)


@dataclass(slots=True)
class DTEParsedData:
    """Parsed DTE feed."""

    updated: str | None
    meters: dict[str, DTEMeter]


async def fetch_dte_xml(session: ClientSession, url: str) -> str:
    """Fetch the DTE Green Button XML from a share URL."""
    try:
        async with session.get(url, timeout=60) as response:
            if response.status >= 400:
                raise DTEDataError(f"DTE URL returned HTTP {response.status}")
            text = await response.text()
    except ClientError as err:
        raise DTEDataError(f"Could not connect to DTE URL: {err}") from err

    if "<feed" not in text or "UsagePoint" not in text:
        raise DTEDataError("The DTE URL did not return a Green Button XML feed.")

    return text


def parse_dte_green_button_xml(xml_text: str) -> DTEParsedData:
    """Parse a DTE Green Button XML feed with multiple usage points."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as err:
        raise DTEDataError(f"Invalid XML from DTE: {err}") from err

    updated = _text(root.find("atom:updated", NS))
    entries = root.findall("atom:entry", NS)

    usage_points: dict[str, dict[str, Any]] = {}
    reading_type_power: dict[str, int] = {}

    # First pass: discover usage points and reading type scalers.
    for entry in entries:
        title = _text(entry.find("atom:title", NS)) or ""
        self_href = _link_href(entry, "self")

        usage_point = entry.find(".//espi:UsagePoint", NS)
        if usage_point is not None and self_href:
            meter_id = _usage_point_id_from_href(self_href)
            if meter_id:
                kind = _text(usage_point.find(".//espi:ServiceCategory/espi:kind", NS))
                service = _service_from_kind(kind, title)
                usage_points[meter_id] = {
                    "title": title,
                    "service": service,
                }

        reading_type = entry.find(".//espi:ReadingType", NS)
        if reading_type is not None and self_href:
            multiplier_text = _text(
                reading_type.find("espi:powerOfTenMultiplier", NS)
            )
            try:
                multiplier = int(multiplier_text or "0")
            except ValueError:
                multiplier = 0
            reading_type_power[self_href] = multiplier

    meters: dict[str, DTEMeter] = {}
    service_counts: dict[str, int] = {"electric": 0, "gas": 0}

    # Second pass: parse interval blocks for each usage point.
    for entry in entries:
        self_href = _link_href(entry, "self") or ""
        if "IntervalBlock" not in self_href:
            continue

        meter_id = _usage_point_id_from_href(self_href)
        if not meter_id or meter_id not in usage_points:
            continue

        service = usage_points[meter_id]["service"]
        if service not in ("electric", "gas"):
            continue

        if meter_id not in meters:
            service_counts[service] += 1
            if service == "electric":
                name = f"Electric Meter {service_counts[service]}"
                unit = "kWh"
            else:
                name = "Gas Meter" if service_counts[service] == 1 else f"Gas Meter {service_counts[service]}"
                unit = "CCF"

            meters[meter_id] = DTEMeter(
                meter_id=meter_id,
                name=name,
                service=service,
                unit=unit,
            )

        multiplier = _reading_multiplier_for_entry(entry, service, reading_type_power)
        for interval_reading in entry.findall(".//espi:IntervalReading", NS):
            start = _int_text(
                interval_reading.find("espi:timePeriod/espi:start", NS)
            )
            duration = _int_text(
                interval_reading.find("espi:timePeriod/espi:duration", NS)
            )
            raw_value = _float_text(interval_reading.find("espi:value", NS))
            if start is None or duration is None or raw_value is None:
                continue

            if service == "electric":
                # DTE's human export displays 603 as 0.603 kWh. Treat raw values
                # as Wh and expose kWh for Home Assistant's energy dashboard.
                usage = raw_value / 1000.0
            else:
                # DTE's gas ReadingType uses CCF with powerOfTenMultiplier -3.
                # Example: raw 1400 => 1.400 CCF.
                usage = raw_value * (10 ** multiplier)

            meters[meter_id].intervals.append(
                DTEInterval(start=start, duration=duration, usage=usage)
            )

    if not meters:
        raise DTEDataError("No electric or gas interval readings were found in the DTE XML.")

    return DTEParsedData(updated=updated, meters=meters)


def _reading_multiplier_for_entry(
    entry: ET.Element,
    service: str,
    reading_type_power: dict[str, int],
) -> int:
    """Return the multiplier to apply to raw interval readings."""
    if service == "electric":
        return -3

    for link in entry.findall("atom:link", NS):
        href = link.attrib.get("href", "")
        if href in reading_type_power:
            return reading_type_power[href]
        if href.startswith("ReadingType/gas") and "ReadingType/gas" in reading_type_power:
            return reading_type_power["ReadingType/gas"]

    # DTE gas data uses CCF with powerOfTenMultiplier -3.
    return -3


def _service_from_kind(kind: str | None, title: str) -> str:
    """Map DTE ServiceCategory kind/title to a service name."""
    lowered = title.lower()
    if kind == "0" or "electric" in lowered:
        return "electric"
    if kind == "1" or "gas" in lowered:
        return "gas"
    return "unknown"


def _usage_point_id_from_href(href: str) -> str | None:
    """Extract UsagePoint UUID from a DTE Atom link href."""
    marker = "/UsagePoint/"
    if marker not in href:
        return None
    tail = href.split(marker, 1)[1]
    return tail.split("/", 1)[0] or None


def _link_href(entry: ET.Element, rel: str) -> str | None:
    """Return the href for the first link with rel."""
    for link in entry.findall("atom:link", NS):
        if link.attrib.get("rel") == rel:
            return link.attrib.get("href")
    return None


def _text(element: ET.Element | None) -> str | None:
    """Get stripped text from an XML element."""
    if element is None or element.text is None:
        return None
    return element.text.strip()


def _int_text(element: ET.Element | None) -> int | None:
    """Read an integer XML text value."""
    value = _text(element)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _float_text(element: ET.Element | None) -> float | None:
    """Read a float XML text value."""
    value = _text(element)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
