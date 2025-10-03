#!/usr/bin/env python3
"""Parse the novelan demo.dta data logger file.

The Android app ships `assets/demo.dta` as a canned log.  The on-device
`DataLoggerManager` parses it into four timeseries (TVL, TRL, TBW, TA).  This
script mirrors that logic so we can inspect the payload on a desktop machine.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

# Constants lifted from the app's DataLoggerManager implementation
VERSION_9002 = 9002
ACTION_FLAG_EXTRA1 = 0x0001
ACTION_FLAG_EXTRA2 = 0x0002
ACTION_FLAG_EXTRA3 = 0x0008
ACTION_FLAG_EXTRA4 = 0x1000  # PlaybackStateCompat.ACTION_SKIP_TO_QUEUE_ITEM


@dataclass
class Record:
    timestamp: int
    supply_temp_c: float
    return_temp_c: float
    hotwater_temp_c: float
    outdoor_temp_c: float


def _read_u32(buffer: bytes, offset: int) -> Tuple[int, int]:
    return int.from_bytes(buffer[offset : offset + 4], "little", signed=False), offset + 4


def _read_u16(buffer: bytes, offset: int) -> Tuple[int, int]:
    return int.from_bytes(buffer[offset : offset + 2], "little", signed=False), offset + 2


def _read_i16(buffer: bytes, offset: int) -> Tuple[int, int]:
    return int.from_bytes(buffer[offset : offset + 2], "little", signed=True), offset + 2


def parse_demo_dta(payload: bytes) -> List[Record]:
    offset = 0
    version, offset = _read_u32(payload, offset)
    flags, offset = _read_u32(payload, offset)
    # The next 2 bytes are unused in the Android parser.
    _, offset = _read_u16(payload, offset)

    block_size = None
    if version >= VERSION_9002:
        block_size, offset = _read_u16(payload, offset)

    records: List[Record] = []

    while offset < len(payload):
        block_start = offset
        timestamp, offset = _read_u32(payload, offset)

        # Guard against zeroed padding at the tail of the file.
        if timestamp == 0:
            break

        supply_raw, offset = _read_i16(payload, offset)
        return_raw, offset = _read_i16(payload, offset)
        offset += 6  # unused fields in the original log format

        hotwater_raw, offset = _read_i16(payload, offset)
        offset += 2  # unknown / reserved

        outdoor_raw, offset = _read_i16(payload, offset)
        offset += 10  # more reserved bytes

        if flags & ACTION_FLAG_EXTRA1:
            offset += 26
        if flags & ACTION_FLAG_EXTRA2:
            offset += 18

        offset += 24  # always present

        if flags & ACTION_FLAG_EXTRA3:
            offset += 28
        if flags & ACTION_FLAG_EXTRA4:
            offset += 10

        if block_size and version >= VERSION_9002:
            # Align to the block boundary in case optional sections were absent.
            offset = block_start + block_size

        records.append(
            Record(
                timestamp=timestamp,
                supply_temp_c=supply_raw / 10.0,
                return_temp_c=return_raw / 10.0,
                hotwater_temp_c=hotwater_raw / 10.0,
                outdoor_temp_c=outdoor_raw / 10.0,
            )
        )

    return records


def write_csv(records: Iterable[Record], out_path: Path) -> None:
    with out_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "supply_c", "return_c", "hotwater_c", "outdoor_c"])
        for rec in records:
            writer.writerow([
                rec.timestamp,
                f"{rec.supply_temp_c:.1f}",
                f"{rec.return_temp_c:.1f}",
                f"{rec.hotwater_temp_c:.1f}",
                f"{rec.outdoor_temp_c:.1f}",
            ])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("demo_dta", type=Path, help="Path to assets/demo.dta")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("demo_dta.csv"),
        help="Where to write the extracted CSV (default: demo_dta.csv)",
    )
    args = parser.parse_args()

    payload = args.demo_dta.read_bytes()
    records = parse_demo_dta(payload)
    if not records:
        raise SystemExit("No records decoded from demo.dta")

    write_csv(records, args.out)
    print(f"Decoded {len(records)} log entries to {args.out}")


if __name__ == "__main__":
    main()
