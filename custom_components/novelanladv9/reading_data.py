import asyncio
import logging
from contextlib import suppress
from datetime import datetime

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


LOGGER = logging.getLogger(__name__)


class ControlCommandError(Exception):
    """Raised when the heat pump rejects a control command."""


def _normalize_label(raw) -> str:
    """Extract a readable label from XML fragments."""
    if isinstance(raw, list):
        for item in raw:
            text = _normalize_label(item)
            if text:
                return text
        return ""
    if isinstance(raw, dict):
        for key in ("#text", "@name", "name"):
            if key in raw:
                text = _normalize_label(raw[key])
                if text:
                    return text
        return ""
    if raw is None:
        return ""
    return str(raw)


def determine_sensor_type(reading_name, reading_value):
    if "Temperaturen" in reading_name:
        if "°C" in str(reading_value):
            return "temperature"
        elif "K" in str(reading_value):
            return "temperature.kelvin"
    elif "Eingänge" in reading_name:
        if str(reading_value) in ["Ein", "Aus"]:
            return "binary_sensor"
        elif "bar" in str(reading_value):
            return "pressure"
        elif "l/h" in str(reading_value):
            return "flow_rate"
    elif "Ausgänge" in reading_name:
        if str(reading_value) in ["Ein", "Aus"]:
            return "binary_sensor"
        elif "V" in str(reading_value):
            return "voltage"
        elif "%" in str(reading_value):
            return "percentage"
        elif "RPM" in str(reading_value):
            return "speed"
    elif "Ablaufzeiten" in reading_name:
        return "duration"
    elif "Betriebsstunden" in reading_name:
        return "operating_hours"
    elif "Fehlerspeicher" in reading_name or "Abschaltungen" in reading_name:
        return "error_log"
    elif "Anlagenstatus" in reading_name:
        return "system_status"
    elif "Wärmemenge" in reading_name:
        return "energy"
    else:
        return "Unknown"

async def fetch_data(ip_address, pin="999999"):
    """Fetch current readings and return a flat dict of name -> value.

    Keys are built as "<group>_<name>", e.g. "Temperaturen_Vorlauf".
    """
    ws_url = f"ws://{ip_address}:8214/"
    ws_com_login = f"LOGIN;{pin}"

    async with websockets.connect(ws_url, subprotocols=['Lux_WS'], open_timeout=5, ping_timeout=10, close_timeout=2) as websocket:
        res: dict[str, str] = {}
        await websocket.send(ws_com_login)
        greeting = await websocket.recv()
        d = xmltodict.parse(greeting)
        nav_items = d['Navigation']['item']
        if isinstance(nav_items, dict):
            nav_items = [nav_items]
        information = next((c for c in nav_items if c.get('name') in ('Informationen', 'Information')), None)
        if not information:
            return {}
        await websocket.send(f"GET;{information['@id']}")
        p = await websocket.recv()
        d = xmltodict.parse(p)
        content_items = d.get('Content', {}).get('item', [])
        if isinstance(content_items, dict):
            content_items = [content_items]
        for group in content_items:
            gname = _normalize_label(group.get('name')).strip()
            items = group.get('item')
            if isinstance(items, dict):
                items = [items]
            if not isinstance(items, list):
                continue
            for it in items:
                if not isinstance(it, dict):
                    continue
                name = _normalize_label(it.get('name')).strip()
                value = it.get('value')
                if gname and name is not None:
                    key = f"{gname}_{name}"
                    res[key] = value
        res['Time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return res


async def fetch_controls(ip_address, pin="999999"):
    ws_url = f"ws://{ip_address}:8214/"
    ws_com_login = f"LOGIN;{pin}"

    async with websockets.connect(ws_url, subprotocols=['Lux_WS'], open_timeout=5, ping_timeout=10, close_timeout=2) as websocket:
        await websocket.send(ws_com_login)
        greeting = await websocket.recv()
        d = xmltodict.parse(greeting)
        nav_items = d['Navigation']['item']
        if isinstance(nav_items, dict):
            nav_items = [nav_items]

        def _match_name(node, candidates):
            name = _normalize_label(node.get('name')).strip() if node else ""
            return name in candidates

        settings = next((c for c in nav_items if _match_name(c, {"Einstellungen", "Settings"})), None)
        if not settings:
            return []

        settings_items = settings.get('item')
        if isinstance(settings_items, dict):
            settings_items = [settings_items]

        operate = next((c for c in settings_items or [] if _match_name(c, {"Betriebsart"})), None)
        if not operate or '@id' not in operate:
            return []

        operate_id = operate['@id']
        await websocket.send(f"GET;{operate_id}")
        p = await websocket.recv()
        content = xmltodict.parse(p)

        items = content.get('Content', {}).get('item', [])
        if isinstance(items, dict):
            items = [items]

        controls: list[dict[str, str]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = _normalize_label(item.get('name')).strip()
            if not name:
                continue
            options = item.get('option')
            if isinstance(options, dict):
                options = [options]
            normalized_options = []
            if isinstance(options, list):
                for opt in options:
                    if not isinstance(opt, dict):
                        continue
                    normalized_options.append({
                        'value': opt.get('@value'),
                        'label': _normalize_label(opt.get('#text') or opt.get('value')).strip(),
                    })
            controls.append({
                '@id': item.get('@id'),
                'name': name,
                'value': item.get('value'),
                'raw': item.get('raw'),
                'options': normalized_options,
                'page_id': operate_id,
            })

        return controls


async def fetch_setpoints(ip_address, pin="999999"):
    """Discover numeric setpoint controls for hot water and heating limits.

    Returns a dict keyed by human-readable name with values containing
    control metadata: { 'id': str, 'name': str, 'value': str }
    """
    ws_url = f"ws://{ip_address}:8214/"
    ws_com_login = f"LOGIN;{pin}"

    targets = {
        "Warmwasser-Soll",
        "Rückl.-Begr.",
        "Min. Rückl.Solltemp.",
        "Max.Warmwassertemp.",
    }

    def collect_controls(root):
        found: dict[str, dict[str, str]] = {}

        def walk(node, parent_id=None):
            if isinstance(node, dict):
                current_id = node.get('@id') or parent_id
                name = node.get('name')
                if isinstance(name, list):
                    name = name[0] if name else None
                if name and ('@id' in node) and ('value' in node or 'option' in node):
                    label = _normalize_label(name).strip()
                    if label:
                        found[label] = {
                            'id': node.get('@id'),
                            'name': label,
                            'value': node.get('value'),
                            'raw': node.get('raw'),
                            'options': node.get('option'),
                            'page_id': parent_id,
                        }
                for value in node.values():
                    walk(value, current_id)
            elif isinstance(node, list):
                for value in node:
                    walk(value, parent_id)

        walk(root)
        return found

    async with websockets.connect(ws_url, subprotocols=['Lux_WS'], open_timeout=5, ping_timeout=10, close_timeout=2) as websocket:
        await websocket.send(ws_com_login)
        greeting = await websocket.recv()
        d = xmltodict.parse(greeting)
        nav_items = d['Navigation']['item']
        if isinstance(nav_items, dict):
            nav_items = [nav_items]

        results = {}

        # Probe Einstellungen (Temperaturen and System Einstellung)
        settings = next((c for c in nav_items if c.get('name') in ('Einstellungen', 'Settings')), None)
        if settings:
            await websocket.send(f"GET;{settings['@id']}")
            content = xmltodict.parse(await websocket.recv())
            results.update(collect_controls(content))

        # Also look at Informationen (some controllers expose *-Soll here)
        information = next((c for c in nav_items if c.get('name') in ('Informationen', 'Information')), None)
        if information:
            await websocket.send(f"GET;{information['@id']}")
            content = xmltodict.parse(await websocket.recv())
            results.update(collect_controls(content))

        return results

async def set_control(ip_address, pin, control_id, value, page_id=None, label=None):
    ws_url = f"ws://{ip_address}:8214/"
    ws_com_login = f"LOGIN;{pin}"

    responses: list[str] = []

    async def _recv_optional(websocket):
        try:
            msg = await asyncio.wait_for(websocket.recv(), timeout=5)
        except (asyncio.TimeoutError, ConnectionClosedError, ConnectionClosed, ConnectionClosedOK):
            return None
        except Exception as err:  # pragma: no cover - unforeseen read failure
            LOGGER.debug("Unexpected read error after command: %s", err)
            return None
        else:
            responses.append(msg)
            return msg

    try:
        async with websockets.connect(
            ws_url,
            subprotocols=['Lux_WS'],
            open_timeout=5,
            ping_timeout=10,
            close_timeout=2,
        ) as websocket:
            await websocket.send(ws_com_login)
            greeting = await _recv_optional(websocket)

            nav_page_id = page_id
            if greeting:
                try:
                    nav_root = xmltodict.parse(greeting)
                except Exception as err:  # pragma: no cover
                    LOGGER.debug("Failed to parse navigation payload: %s", err)
                else:
                    items = nav_root.get('Navigation', {}).get('item')
                    if isinstance(items, dict):
                        items = [items]
                    if isinstance(items, list):
                        settings_node = next(
                            (
                                node
                                for node in items
                                if _normalize_label(node.get('name')).strip() in {"Einstellungen", "Settings"}
                            ),
                            None,
                        )
                        if settings_node:
                            children = settings_node.get('item')
                            if isinstance(children, dict):
                                children = [children]
                            if isinstance(children, list):
                                operate_node = next(
                                    (
                                        child
                                        for child in children
                                        if isinstance(child, dict)
                                        and _normalize_label(child.get('name')).strip() == 'Betriebsart'
                                        and child.get('@id')
                                    ),
                                    None,
                                )
                                if operate_node:
                                    nav_page_id = operate_node.get('@id')

            active_id = control_id

            if nav_page_id:
                LOGGER.debug("Opening outer page %s", nav_page_id)
                await websocket.send(f"GET;{nav_page_id}")
                outer_payload = await _recv_optional(websocket)
            else:
                outer_payload = None

            if outer_payload and label:
                try:
                    outer_content = xmltodict.parse(outer_payload)
                except Exception as err:  # pragma: no cover
                    LOGGER.debug("Failed to parse outer page: %s", err)
                else:
                    candidates = outer_content.get('Content', {}).get('item', [])
                    if isinstance(candidates, dict):
                        candidates = [candidates]
                    for candidate in candidates:
                        if not isinstance(candidate, dict):
                            continue
                        if _normalize_label(candidate.get('name')).strip() == label and candidate.get('@id'):
                            active_id = candidate.get('@id')
                            break

            if label and not active_id:
                LOGGER.debug("Falling back to REFRESH lookup for %s", label)
                await websocket.send("REFRESH")
                refresh_payload = await _recv_optional(websocket)
                if refresh_payload:
                    try:
                        refresh_content = xmltodict.parse(refresh_payload)
                    except Exception as err:  # pragma: no cover
                        LOGGER.debug("Failed to parse refresh payload: %s", err)
                    else:
                        items = refresh_content.get('values', {}).get('item', [])
                        if isinstance(items, dict):
                            items = [items]
                        for item in items:
                            if not isinstance(item, dict):
                                continue
                            if _normalize_label(item.get('name')).strip() == label and item.get('@id'):
                                active_id = item.get('@id')
                                break

            if not active_id:
                raise ControlCommandError("Missing control id for set_control")

            prefixed_id = active_id
            if not str(active_id).startswith("set_"):
                prefixed_id = f"set_{active_id}"

            set_payload = f"SET;{prefixed_id};{value}"
            LOGGER.debug("Sending %s", set_payload)
            await websocket.send(set_payload)
            await _recv_optional(websocket)
            await asyncio.sleep(0.05)

            LOGGER.debug("Sending REFRESH (post-SET)")
            await websocket.send("REFRESH")
            await _recv_optional(websocket)

            LOGGER.debug("Sending SAVE;1")
            await websocket.send("SAVE;1")
            await _recv_optional(websocket)

            LOGGER.debug("Sending REFRESH (post-SAVE)")
            await websocket.send("REFRESH")
            refresh = await _recv_optional(websocket)

            LOGGER.debug("Sending final REFRESH")
            await websocket.send("REFRESH")
            final_refresh = await _recv_optional(websocket)

            return final_refresh or refresh or (responses[-1] if responses else None)
    except (ConnectionClosedError, ConnectionClosed) as err:
        LOGGER.warning(
            "Websocket closed while setting %s on %s: %s",
            control_id,
            ip_address,
            err,
        )
        if responses:
            return responses[-1]
        if prefixed_id:
            raise ControlCommandError(err) from err
        return None
    except (asyncio.TimeoutError, WebSocketException, OSError) as err:
        LOGGER.error(
            "Failed to send control command %s on %s: %s",
            control_id,
            ip_address,
            err,
        )
        raise ControlCommandError(err) from err
