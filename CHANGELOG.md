# Changelog

## 0.2.1

- Added imported external statistic for aggregate electric total.
- Keeps README statistic IDs aligned with generated statistics.

## 0.2.0

- Added external statistics importer for Home Assistant long-term statistics.
- Imports DTE interval readings using the original interval timestamp.
- Keeps imports rolling-window safe by storing the latest imported interval and cumulative sum.
- Keeps live cumulative sensors for visibility/debugging.

## 0.1.0

- Initial multi-meter DTE Green Button parser.
- Supports two electric meters, electric total, and gas meter from one combined DTE URL.
