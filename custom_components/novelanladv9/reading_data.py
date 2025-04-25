# ws://192.168.1.166:8214/
# "LOGIN;999999"
# "GET;0x48f488" #request temp page
# "GET;0x3e7478" #request overview page

# "REFRESH"
ws_url = "ws://192.168.1.166:8214/"
ws_com_login = "LOGIN;999999"

#!/usr/bin/env python

import asyncio
import websockets
import xmltodict
import sys, os
from gzip import open
from datetime import datetime

if len(sys.argv) == 2:
    csv_filename = sys.argv[1]
    if not csv_filename.endswith('.gz'):
        csv_filename += '.gz'
    month = datetime.now().strftime("%Y-%m")
    csv_filename = os.path.join(os.path.dirname(csv_filename), month+'_'+os.path.basename(csv_filename))

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


async def hello():

    async with websockets.connect(ws_url, subprotocols=['Lux_WS']) as websocket:
        res = {}
        await websocket.send(ws_com_login)
        greeting = await websocket.recv()
        d = xmltodict.parse(greeting)
        nid=[c['@id'] for c in d['Navigation']['item'] if c['name'] == 'Informationen'][0]
        await websocket.send(f"GET;{nid}")
        p = await websocket.recv()
        d = xmltodict.parse(p)
        for k in d['Content']['item']:
            #if k['name'][0] not in ['Wärmemenge', 'Temperaturen']:
            #    continue
            prefix = k['name'][0]
            for l in k['item']:
                if not isinstance(l, dict):
                    continue
                sensor_type = determine_sensor_type(f"{prefix}_{l['name']}", l['value'])
                res[f"{prefix}_{l['name']}"] = l['value']
                print(f"{prefix}_{l['name']} = {l['value']} ; {sensor_type}")
        res['Time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        temp = int(float(res['Temperaturen_Aussentemperatur'][:-2])*100)
        t = int.from_bytes(temp.to_bytes(2,'big', signed=True), 'big', signed=False)




asyncio.get_event_loop().run_until_complete(hello())