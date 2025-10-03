"""List selectable controls exposed by the Home Assistant integration helpers."""

from __future__ import annotations

import argparse
import asyncio
from pprint import pprint

from custom_components.novelanladv9.reading_data import fetch_controls


async def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect available select controls")
    parser.add_argument("--ip", required=True, help="Heat pump IP or hostname")
    parser.add_argument("--pin", default="999999", help="Service PIN")
    args = parser.parse_args()

    controls = await fetch_controls(args.ip, args.pin)
    printable = []
    for ctrl in controls:
        printable.append({
            "name": ctrl.get("name"),
            "value": ctrl.get("value"),
            "raw": ctrl.get("raw"),
            "navigation_id": ctrl.get("page_id"),
            "values_id": ctrl.get("values_id") or ctrl.get("@id"),
            "options": ctrl.get("options"),
        })
    pprint(printable)


if __name__ == "__main__":  # pragma: no cover - manual utility
    asyncio.run(main())
