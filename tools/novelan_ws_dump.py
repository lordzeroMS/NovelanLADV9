"""Dump the navigation tree of a Novelan LADV9 controller for debugging."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections import defaultdict, deque
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import xmltodict
import websockets

try:  # websockets >= 12
    from websockets.exceptions import (
        ConnectionClosed,
        ConnectionClosedError,
        ConnectionClosedOK,
        WebSocketException,
    )
except ImportError:  # pragma: no cover - legacy fallback
    ConnectionClosed = websockets.ConnectionClosed
    ConnectionClosedError = getattr(websockets, "ConnectionClosedError", ConnectionClosed)
    ConnectionClosedOK = getattr(websockets, "ConnectionClosedOK", ConnectionClosed)
    WebSocketException = websockets.WebSocketException


LOGGER = logging.getLogger("novelan_ws_dump")


@dataclass(slots=True)
class QueueNode:
    path: tuple[str, ...]
    node_id: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Traverse the websocket navigation tree exposed by a Novelan LADV9 "
            "heat pump and emit a JSON report for offline inspection."
        )
    )
    parser.add_argument("--ip", required=True, help="Heat pump IP or hostname")
    parser.add_argument("--pin", default="999999", help="Service PIN")
    parser.add_argument(
        "--json-out",
        type=Path,
        default=Path("novelan_ws_dump.json"),
        help="File to store the collected report (defaults to novelan_ws_dump.json)",
    )
    parser.add_argument(
        "--max-nodes",
        type=int,
        default=25,
        help="Maximum number of GET requests to perform",
    )
    parser.add_argument(
        "--include-raw",
        action="store_true",
        help="Include the raw XML payload for each node in the report",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Seconds to wait for each node response",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Maximum reconnect attempts per node",
    )
    parser.add_argument(
        "--max-failures",
        type=int,
        default=200,
        help="Abort after this many nodes are skipped due to repeated failures",
    )
    parser.add_argument(
        "--overview-only",
        action="store_true",
        help="Stop after collecting the first overview node",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser


def _enumerate_children(node: Any) -> Iterable[tuple[str, str]]:
    if isinstance(node, dict):
        name = node.get("name")
        node_id = node.get("@id")
        if isinstance(name, list):  # some controllers wrap name in list
            name = name[0] if name else None
        if name and node_id:
            yield name, node_id
        for value in node.values():
            yield from _enumerate_children(value)
    elif isinstance(node, list):
        for value in node:
            yield from _enumerate_children(value)


def _extract_entries(node: Any) -> list[dict[str, Any]]:
    res: list[dict[str, Any]] = []
    if isinstance(node, dict):
        name = node.get("name")
        value = node.get("value")
        options = node.get("option")
        if name and (value is not None or options is not None):
            entry: dict[str, Any] = {"name": name}
            if value is not None:
                entry["value"] = value
            if options is not None:
                entry["options"] = _simplify_options(options)
            res.append(entry)
        for child in node.values():
            res.extend(_extract_entries(child))
    elif isinstance(node, list):
        for child in node:
            res.extend(_extract_entries(child))
    return res


def _simplify_options(options: Any) -> list[str] | None:
    if isinstance(options, list):
        simplified: list[str] = []
        for opt in options:
            if isinstance(opt, dict):
                value = opt.get("@value") or opt.get("value")
                if value is not None:
                    simplified.append(str(value))
            else:
                simplified.append(str(opt))
        return simplified
    if isinstance(options, dict):
        value = options.get("@value") or options.get("value")
        return [str(value)] if value is not None else None
    if options is not None:
        return [str(options)]
    return None


async def _open_connection(args: argparse.Namespace):
    ws_url = f"ws://{args.ip}:8214/"
    websocket = await websockets.connect(
        ws_url,
        subprotocols=["Lux_WS"],
        open_timeout=5,
        ping_timeout=10,
        close_timeout=2,
    )
    await websocket.send(f"LOGIN;{args.pin}")
    greeting = await websocket.recv()
    parsed = xmltodict.parse(greeting)
    return websocket, parsed


async def collect_report(args: argparse.Namespace) -> dict[str, Any]:
    websocket, parsed = await _open_connection(args)
    report: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    nav_items = parsed.get("Navigation", {}).get("item")
    items = nav_items if isinstance(nav_items, list) else [nav_items]

    queue: deque[QueueNode] = deque()
    for item in filter(None, items):
        name = item.get("name") or "<unnamed>"
        node_id = item.get("@id")
        if isinstance(name, list):
            name = name[0] if name else "<unnamed>"
        if node_id:
            queue.append(QueueNode((str(name),), node_id))

    seen: set[str] = set()
    retries: defaultdict[str, int] = defaultdict(int)
    skipped_count = 0

    try:
        while queue and len(report) < args.max_nodes:
            node = queue.popleft()
            if node.node_id in seen:
                continue

            if retries[node.node_id] >= args.retries:
                LOGGER.warning("Skipping %s after %d retries", node.node_id, retries[node.node_id])
                skipped.append({
                    "path": " / ".join(node.path),
                    "id": node.node_id,
                    "attempts": retries[node.node_id],
                })
                skipped_count += 1
                if args.max_failures and skipped_count >= args.max_failures:
                    LOGGER.error(
                        "Reached max failures (%d); aborting traversal", args.max_failures
                    )
                    break
                if args.overview_only:
                    LOGGER.info("Overview-only mode: stopping after skip of %s", node.node_id)
                    break
                continue

            if websocket.closed:
                LOGGER.debug("Re-opening websocket after closure")
                with suppress(ConnectionClosed, ConnectionClosedError, ConnectionClosedOK):
                    await websocket.close()
                websocket, _ = await _open_connection(args)

            LOGGER.debug("Fetching %s", node)

            try:
                await websocket.send(f"GET;{node.node_id}")
                payload = await asyncio.wait_for(websocket.recv(), timeout=args.timeout)
            except (ConnectionClosedError, ConnectionClosed, WebSocketException, asyncio.TimeoutError) as err:
                LOGGER.warning("Connection issue while fetching %s: %s", node.node_id, err)
                retries[node.node_id] += 1
                queue.appendleft(node)
                with suppress(ConnectionClosed, ConnectionClosedError, ConnectionClosedOK):
                    await websocket.close()
                websocket, _ = await _open_connection(args)
                continue

            node_dict = xmltodict.parse(payload)
            entries = _extract_entries(node_dict)

            entry_list = entries if args.overview_only else entries[:20]

            report_entry: dict[str, Any] = {
                "path": " / ".join(node.path),
                "id": node.node_id,
                "entry_count": len(entries),
                "entries": entry_list,
            }

            if args.include_raw:
                report_entry["raw_xml"] = payload
            else:
                report_entry["raw_length"] = len(payload)

            report.append(report_entry)
            seen.add(node.node_id)

            for child_name, child_id in _enumerate_children(node_dict):
                if child_id not in seen:
                    queue.append(QueueNode((*node.path, child_name), child_id))

            if args.overview_only:
                LOGGER.info("Overview-only mode: collected %s; stopping", node.node_id)
                break
    finally:
        with suppress(ConnectionClosed, ConnectionClosedError, ConnectionClosedOK):
            await websocket.close()

    return {"nodes": report, "skipped": skipped}


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")

    try:
        result = asyncio.run(collect_report(args))
    except KeyboardInterrupt:  # pragma: no cover - interactive use
        LOGGER.warning("Interrupted by user")
        raise SystemExit(130)
    except Exception as err:  # pragma: no cover - network failure path
        LOGGER.error("Failed to collect report: %s", err)
        raise SystemExit(1)

    args.json_out.write_text(json.dumps(result, indent=2, sort_keys=True))
    LOGGER.info(
        "Stored %d nodes (skipped %d) in %s",
        len(result.get("nodes", [])),
        len(result.get("skipped", [])),
        args.json_out,
    )


if __name__ == "__main__":  # pragma: no cover - script entry point
    main()
