"""Quick utility to change heat pump operating modes for testing."""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any

from custom_components.novelanladv9.reading_data import (
    ControlCommandError,
    fetch_controls,
    set_control,
)


LOGGER = logging.getLogger("novelan_control_test")


async def _set_mode(
    ip: str,
    pin: str,
    control_name: str,
    new_value: str,
    delay: float,
) -> None:
    controls: list[dict[str, Any]] | dict[str, Any] = await fetch_controls(ip, pin)

    entries: list[dict[str, Any]]
    if isinstance(controls, list):
        entries = controls
    elif isinstance(controls, dict):
        entries = list(controls.values())
    else:
        raise RuntimeError("Unexpected controls payload")

    target = next((entry for entry in entries if entry.get("name") == control_name), None)
    if not target:
        raise SystemExit(f"Control '{control_name}' not found; available: {[e.get('name') for e in entries]}")

    LOGGER.info("Current state: raw=%s value=%s", target.get("raw"), target.get("value"))

    if delay > 0:
        LOGGER.debug("Sleeping %.2f s before issuing SET", delay)
        await asyncio.sleep(delay)

    try:
        response = await set_control(
            ip,
            pin,
            control_id=target.get("@id"),
            value=str(new_value),
            page_id=target.get("page_id"),
            label=target.get("name"),
        )
    except ControlCommandError as err:
        raise SystemExit(f"Failed to set control: {err}") from err

    if response:
        LOGGER.debug("Controller response: %s", response)

    refreshed = await fetch_controls(ip, pin)
    if isinstance(refreshed, list):
        updated = next((entry for entry in refreshed if entry.get("name") == control_name), None)
    else:
        updated = refreshed.get(control_name)

    if updated:
        LOGGER.info(
            "Updated state: raw=%s value=%s",
            updated.get("raw"),
            updated.get("value"),
        )
    else:
        LOGGER.warning("Unable to confirm updated value; control missing in refresh")


def main() -> None:
    parser = argparse.ArgumentParser(description="Set a Novelan heat pump mode for testing")
    parser.add_argument("--ip", required=True, help="Heat pump IP or hostname")
    parser.add_argument("--pin", default="999999", help="Service PIN (default 999999)")
    parser.add_argument("--control", choices=["Heizkreis", "Warmwasser"], help="Control name to change")
    parser.add_argument("--value", required=True, help="Option value to send (e.g. 0 for Automatik)")
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="Seconds to wait before sending the SET command",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    asyncio.run(_set_mode(args.ip, args.pin, args.control, args.value, args.sleep))


if __name__ == "__main__":  # pragma: no cover - manual utility
    main()
