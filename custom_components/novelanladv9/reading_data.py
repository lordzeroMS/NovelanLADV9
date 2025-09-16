import xmltodict
import websockets
from datetime import datetime

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
    ws_url = f"ws://{ip_address}:8214/"
    ws_com_login = f"LOGIN;{pin}"

    async with websockets.connect(ws_url, subprotocols=['Lux_WS']) as websocket:
        res = {}
        await websocket.send(ws_com_login)
        greeting = await websocket.recv()
        d = xmltodict.parse(greeting)
        information_id = [c['@id'] for c in d['Navigation']['item'] if c['name'] == 'Informationen'][0]
        await websocket.send(f"GET;{information_id}")
        p = await websocket.recv()
        d = xmltodict.parse(p)
        for k in d['Content']['item']:
            prefix = k['name'][0]
            for l in k['item']:
                if not isinstance(l, dict):
                    continue
                res[f"{prefix}_{l['name']}"] = l['value']
        res['Time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return res, d['Content']['item']


async def fetch_controls(ip_address, pin="999999"):
    ws_url = f"ws://{ip_address}:8214/"
    ws_com_login = f"LOGIN;{pin}"

    async with websockets.connect(ws_url, subprotocols=['Lux_WS']) as websocket:
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

    async with websockets.connect(ws_url, subprotocols=['Lux_WS']) as websocket:
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
    async with websockets.connect(ws_url, subprotocols=['Lux_WS']) as websocket:
        await websocket.send(ws_com_login)
        await websocket.recv()  # greeting
        await websocket.send(f"SET;{control_id};{value}")
        response = await websocket.recv()
        # Optionally parse response for success
        return response
