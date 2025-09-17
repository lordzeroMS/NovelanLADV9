import asyncio
import logging
from datetime import datetime

import xmltodict
import websockets


LOGGER = logging.getLogger(__name__)

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
            gname = group.get('name')
            items = group.get('item')
            if isinstance(items, dict):
                items = [items]
            if not isinstance(items, list):
                continue
            for it in items:
                if not isinstance(it, dict):
                    continue
                name = it.get('name')
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
        res = {}
        await websocket.send(ws_com_login)
        greeting = await websocket.recv()
        d = xmltodict.parse(greeting)
        settings = [c for c in d['Navigation']['item'] if c['name'] == 'Einstellungen'][0]
        operate_id = [c for c in settings['item'] if c['name'] == 'Betriebsart'][0]['@id']
        await websocket.send(f"GET;{operate_id}")
        p = await websocket.recv()
        d = xmltodict.parse(p)
        return d['Content']['item']


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
        found = {}
        def walk(x):
            if isinstance(x, dict):
                name = x.get('name')
                if isinstance(name, list):
                    name = name[0] if name else None
                if name in targets and ('@id' in x) and ('value' in x or 'option' in x):
                    found[name] = {
                        'id': x.get('@id'),
                        'name': name,
                        'value': x.get('value'),
                    }
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
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

async def set_control(ip_address, pin, control_id, value):
    ws_url = f"ws://{ip_address}:8214/"
    ws_com_login = f"LOGIN;{pin}"

    set_sent = False

    try:
        async with websockets.connect(
            ws_url,
            subprotocols=['Lux_WS'],
            open_timeout=5,
            ping_timeout=10,
            close_timeout=2,
        ) as websocket:
            await websocket.send(ws_com_login)
            await websocket.recv()  # greeting
            await websocket.send(f"SET;{control_id};{value}")
            set_sent = True

            try:
                response = await websocket.recv()
            except websockets.ConnectionClosed as err:
                LOGGER.debug(
                    "Control %s closed without response on %s: %s",
                    control_id,
                    ip_address,
                    err,
                )
                response = None
            except asyncio.TimeoutError as err:
                LOGGER.debug(
                    "Timed out waiting for response after SET for %s (%s): %s",
                    control_id,
                    ip_address,
                    err,
                )
                response = None

            return response
    except websockets.ConnectionClosed as err:
        if set_sent:
            LOGGER.debug(
                "Websocket closed unexpectedly after SET for %s on %s: %s",
                control_id,
                ip_address,
                err,
            )
            return None
        LOGGER.error(
            "Connection closed before SET for %s on %s: %s",
            control_id,
            ip_address,
            err,
        )
        raise
    except (asyncio.TimeoutError, websockets.WebSocketException, OSError) as err:
        LOGGER.error(
            "Failed to send control command %s on %s: %s",
            control_id,
            ip_address,
            err,
        )
        raise
