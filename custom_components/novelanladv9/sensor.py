import logging
from datetime import timedelta
import voluptuous as vol
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import (
    CONF_IP_ADDRESS,
    TEMP_CELSIUS,
    PERCENTAGE,
    PRESSURE_BAR,
    VOLUME_FLOW_RATE_CUBIC_METERS_PER_HOUR,
    ENERGY_KILO_WATT_HOUR,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN
from .reading_data import determine_sensor_type

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=5)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Novelan LADV9 Heat Pump sensors from config entry."""
    ip_address = entry.data[CONF_IP_ADDRESS]

    coordinator = NovelAnLADV9Coordinator(hass, ip_address)
    await coordinator.async_config_entry_first_refresh()

    entities = []

    for name, value in coordinator.data.items():
        sensor_type = determine_sensor_type(name, value)
        entities.append(NovelAnLADV9Sensor(coordinator, name, sensor_type))

    async_add_entities(entities, True)


class NovelAnLADV9Coordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Novelan LADV9 Heat Pump."""

    def __init__(self, hass, ip_address):
        """Initialize."""
        self.ip_address = ip_address
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self):
        """Update data via library."""
        import xmltodict
        import websockets
        from datetime import datetime

        ws_url = f"ws://{self.ip_address}:8214/"
        ws_com_login = "LOGIN;999999"

        try:
            async with websockets.connect(ws_url, subprotocols=['Lux_WS']) as websocket:
                res = {}
                await websocket.send(ws_com_login)
                greeting = await websocket.recv()
                d = xmltodict.parse(greeting)
                nid = [c['@id'] for c in d['Navigation']['item'] if c['name'] == 'Informationen'][0]
                await websocket.send(f"GET;{nid}")
                p = await websocket.recv()
                d = xmltodict.parse(p)
                for k in d['Content']['item']:
                    prefix = k['name'][0]
                    for l in k['item']:
                        if not isinstance(l, dict):
                            continue
                        res[f"{prefix}_{l['name']}"] = l['value']
                res['Time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                return res
        except Exception as e:
            _LOGGER.error(f"Error fetching data: {e}")
            return {}


class NovelAnLADV9Sensor(CoordinatorEntity, SensorEntity):
    """Representation of a Novelan LADV9 Heat Pump sensor."""

    def __init__(self, coordinator, name, sensor_type):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._name = name
        self._sensor_type = sensor_type
        self._attr_unique_id = f"{DOMAIN}_{name}"
        self._attr_name = name.replace('_', ' ')

        # Map sensor types to Home Assistant device classes
        if "Temperature" in sensor_type:
            if "°C" in sensor_type:
                self._attr_native_unit_of_measurement = TEMP_CELSIUS
                self._attr_device_class = "temperature"
            elif "K" in sensor_type:
                self._attr_native_unit_of_measurement = "K"
                self._attr_device_class = "temperature"
        elif "Pressure" in sensor_type:
            self._attr_native_unit_of_measurement = PRESSURE_BAR
            self._attr_device_class = "pressure"
        elif "Flow Rate" in sensor_type:
            self._attr_native_unit_of_measurement = VOLUME_FLOW_RATE_CUBIC_METERS_PER_HOUR
            self._attr_device_class = "volume_flow_rate"
        elif "Energy" in sensor_type:
            self._attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
            self._attr_device_class = "energy"
        elif "Percentage" in sensor_type:
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_device_class = "power_factor"
        elif "Binary" in sensor_type:
            self._attr_device_class = "binary_sensor"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        value = self.coordinator.data.get(self._name)

        # Clean up the value for displaying in Home Assistant
        if "°C" in value:
            return float(value.replace("°C", ""))
        elif "K" in value:
            return float(value.replace("K", ""))
        elif "bar" in value:
            return float(value.replace("bar", ""))
        elif "l/h" in value:
            return int(value.replace("l/h", ""))
        elif "%" in value:
            return float(value.replace("%", ""))
        elif "V" in value:
            return float(value.replace("V", ""))
        elif "RPM" in value:
            return int(value.replace("RPM", ""))
        elif "kWh" in value:
            return float(value.replace("kWh", ""))
        return value