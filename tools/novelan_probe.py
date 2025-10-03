"""Utility helpers to probe a Novelan LADV9 heat pump via websocket."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from custom_components.novelanladv9.reading_data import (
    ControlCommandError,
    determine_sensor_type,
    fetch_controls,
    fetch_data,
    fetch_setpoints,
)


LOGGER = logging.getLogger("novelan_probe")


@dataclass(slots=True)
class ProbeResult:
    readings: dict[str, Any] | None = None
    setpoints: dict[str, Any] | None = None
    controls: Any | None = None
    failures: list[str] | None = None


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Gather diagnostics from a Novelan LADV9 heat pump using the same "
            "helpers as the Home Assistant integration."
        )
    )
    parser.add_argument("--ip", required=True, help="Heat pump IP or hostname")
    parser.add_argument("--pin", default="999999", help="Service PIN, defaults to 999999")
    parser.add_argument(
        "--sections",
        choices=["readings", "setpoints", "controls", "all"],
        default="all",
        help="Which data to fetch",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        help="Optional path to write the gathered data as JSON",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Overall timeout in seconds for each section",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser


async def run_probe(args: argparse.Namespace) -> ProbeResult:
    wanted = {args.sections} if args.sections != "all" else {"readings", "setpoints", "controls"}
    result = ProbeResult(failures=[])

    async def with_timeout(coro):
        return await asyncio.wait_for(coro, timeout=args.timeout)

    if "readings" in wanted:
        try:
            readings = await with_timeout(fetch_data(args.ip, args.pin))
        except Exception as err:  # pragma: no cover - network failure path
            msg = f"readings: {err}"
            LOGGER.error(msg)
            result.failures.append(msg)
        else:
            result.readings = readings

    if "setpoints" in wanted:
        try:
            setpoints = await with_timeout(fetch_setpoints(args.ip, args.pin))
        except Exception as err:  # pragma: no cover - network failure path
            msg = f"setpoints: {err}"
            LOGGER.error(msg)
            result.failures.append(msg)
        else:
            result.setpoints = setpoints

    if "controls" in wanted:
        try:
            controls = await with_timeout(fetch_controls(args.ip, args.pin))
        except ControlCommandError as err:
            msg = f"controls rejected: {err}"
            LOGGER.error(msg)
            result.failures.append(msg)
        except Exception as err:  # pragma: no cover - network failure path
            msg = f"controls: {err}"
            LOGGER.error(msg)
            result.failures.append(msg)
        else:
            result.controls = controls

    if not result.failures:
        result.failures = None

    return result


def print_summary(probe: ProbeResult) -> None:
    if probe.readings is not None:
        LOGGER.info("Fetched %d readings", len(probe.readings))
        for key in sorted(probe.readings)[:10]:
            value = probe.readings[key]
            LOGGER.info("  %s = %s (type: %s)", key, value, determine_sensor_type(key, value))
        if len(probe.readings) > 10:
            LOGGER.info("  ... %d additional readings omitted", len(probe.readings) - 10)
    else:
        LOGGER.info("No readings fetched")

    if probe.setpoints is not None:
        LOGGER.info("Fetched %d setpoints", len(probe.setpoints))
        for name, meta in sorted(probe.setpoints.items()):
            LOGGER.info("  %s -> id=%s value=%s", name, meta.get("id"), meta.get("value"))
    else:
        LOGGER.info("No setpoints fetched")

    if probe.controls is not None:
        LOGGER.info("Fetched raw controls payload")
        if isinstance(probe.controls, dict):
            LOGGER.info("  Keys available: %s", list(probe.controls.keys()))
        elif isinstance(probe.controls, list):
            names = [str(entry.get("name")) for entry in probe.controls if isinstance(entry, dict)]
            LOGGER.info("  Entries: %s", names[:10])
        else:
            LOGGER.info("  Controls type: %s", type(probe.controls).__name__)
    else:
        LOGGER.info("No controls payload fetched")

    if probe.failures:
        LOGGER.error("Failures: %s", "; ".join(probe.failures))
    else:
        LOGGER.info("All requested sections completed successfully")


def export_json(path: Path, probe: ProbeResult) -> None:
    payload = {
        "readings": probe.readings,
        "setpoints": probe.setpoints,
        "controls": probe.controls,
        "failures": probe.failures,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    LOGGER.info("Wrote diagnostics to %s", path)


def main() -> None:
    args = build_arg_parser().parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")
    try:
        probe = asyncio.run(run_probe(args))
    except KeyboardInterrupt:  # pragma: no cover - interactive use
        LOGGER.warning("Interrupted by user")
        raise SystemExit(130)

    print_summary(probe)

    if args.json_out:
        export_json(args.json_out, probe)


if __name__ == "__main__":  # pragma: no cover - script entry point
    main()
