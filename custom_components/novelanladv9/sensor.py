import logging
from datetime import timedelta
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.components.sensor import (
    SensorEntity, SensorDeviceClass, SensorStateClass
)
from homeassistant.const import (
    CONF_IP_ADDRESS,
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfPressure,
    UnitOfEnergy,
    UnitOfElectricPotential,
    UnitOfTime,
)

from .const import DOMAIN, CONF_IP_ADDRESS, CONF_PIN
from .reading_data import determine_sensor_type, fetch_data

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=1)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Novelan LADV9 Heat Pump sensors from config entry."""
    ip_address = entry.data[CONF_IP_ADDRESS]
    pin = entry.data.get(CONF_PIN, "999999")

    coordinator = NovelAnLADV9Coordinator(hass, ip_address, pin)
    await coordinator.async_config_entry_first_refresh()

    entities = []

    # Create device info for this specific heat pump
    device_info = {
        "identifiers": {(DOMAIN, ip_address)},
        "name": f"Novelan LADV9 ({ip_address})",
        "manufacturer": "Novelan",
        "model": "LADV9"
    }

    for name, value in coordinator.data.items():
        # Skip sensors with unwanted names
        if (name.lower() == "time" or
            name.startswith("Fehlerspeicher") or
            name.startswith("Abschaltungen")):
            continue

        sensor_type = determine_sensor_type(name, value)
        entities.append(NovelAnLADV9Sensor(coordinator, name, sensor_type, device_info))

    async_add_entities(entities, True)


class NovelAnLADV9Coordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Novelan LADV9 Heat Pump."""

    def __init__(self, hass, ip_address, pin="999999"):
        """Initialize."""
        self.ip_address = ip_address
        self.pin = pin
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self):
        """Update data via library."""
        try:
            data = await fetch_data(self.ip_address, self.pin)
            if not isinstance(data, dict):
                raise UpdateFailed("Unexpected data format from fetch_data")
            return data
        except Exception as e:
            raise UpdateFailed(f"Error fetching data from {self.ip_address}: {e}")


class NovelAnLADV9Sensor(CoordinatorEntity, SensorEntity):
    """Representation of a Novelan LADV9 Heat Pump sensor."""

    def __init__(self, coordinator, name, sensor_type, device_info):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._name = name
        self._sensor_type = sensor_type

        # Make unique ID specific to this IP
        ip_id = coordinator.ip_address.replace('.', '_')
        self._attr_unique_id = f"{DOMAIN}_{ip_id}_{name}"
        self._attr_name = name.replace('_', ' ')

        # Assign device info
        self._attr_device_info = device_info
        _LOGGER.debug(f"Creating sensor: {name} with type {sensor_type}")

        # Map sensor types to Home Assistant device classes (using lowercase comparison)
        sensor_type_lower = sensor_type.lower()

        if "temperatur" in sensor_type_lower or sensor_type_lower == "temperature":
            if "kelvin" in sensor_type_lower or "k" in sensor_type_lower:
                self._attr_native_unit_of_measurement = "K"
                self._attr_device_class = SensorDeviceClass.TEMPERATURE
            else:
                # Default for all temperature sensors (including those with °C)
                self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
                self._attr_device_class = SensorDeviceClass.TEMPERATURE
        elif "pressure" in sensor_type_lower:
            self._attr_native_unit_of_measurement = UnitOfPressure.BAR
            self._attr_device_class = SensorDeviceClass.PRESSURE
        elif "flow_rate" in sensor_type_lower:
            # Report native unit as liters per hour.
            self._attr_native_unit_of_measurement = "L/h"
            self._attr_device_class = None
        elif "energy" in sensor_type_lower:
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_device_class = SensorDeviceClass.ENERGY
        elif "percentage" in sensor_type_lower:
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_device_class = None
        elif "binary_sensor" in sensor_type_lower:
            self._attr_device_class = None
        elif "voltage" in sensor_type_lower:
            self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
            self._attr_device_class = SensorDeviceClass.VOLTAGE
        elif "speed" in sensor_type_lower:
            # The device reports RPM values
            self._attr_native_unit_of_measurement = "RPM"
            self._attr_device_class = None
        elif "duration" in sensor_type_lower:
            self._attr_native_unit_of_measurement = UnitOfTime.HOURS
            self._attr_device_class = SensorDeviceClass.DURATION
        elif "operating_hours" in sensor_type_lower:
            self._attr_native_unit_of_measurement = UnitOfTime.HOURS
            self._attr_device_class = SensorDeviceClass.DURATION
        elif "error_log" in sensor_type_lower or "system_status" in sensor_type_lower:
            # Text-based sensors
            self._attr_device_class = None
        else:
            self._attr_device_class = None
            self._attr_native_unit_of_measurement = None
            _LOGGER.warning(f"Unknown sensor type '{sensor_type}' for {name}")

        # Set appropriate state class based on device class
        if self._attr_device_class in [
            SensorDeviceClass.TEMPERATURE, SensorDeviceClass.PRESSURE,
            SensorDeviceClass.VOLTAGE, SensorDeviceClass.SPEED,
            SensorDeviceClass.POWER_FACTOR, SensorDeviceClass.VOLUME_FLOW_RATE,
            SensorDeviceClass.DURATION
        ]:
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif self._attr_device_class == SensorDeviceClass.ENERGY:
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING

        _LOGGER.debug(f"Sensor {name} configured with device_class: {getattr(self, '_attr_device_class', None)}, "
                     f"unit: {getattr(self, '_attr_native_unit_of_measurement', None)}, "
                     f"state_class: {getattr(self, '_attr_state_class', None)}")

    @property
    def native_value(self):
        """Return the state of the sensor."""
        value = self.coordinator.data.get(self._name)

        # Handle None values
        if value is None:
            return None

        try:
            # Clean up the value for displaying in Home Assistant
            if isinstance(value, str):
                if "°C" in value:
                    return float(value.replace("°C", "").strip())
                elif "K" in value:
                    return float(value.replace("K", "").strip())
                elif "bar" in value:
                    return float(value.replace("bar", "").strip())
                elif "l/h" in value:
                    # Handle special case like '--- '
                    cleaned_value = value.replace("l/h", "").strip()
                    return int(cleaned_value) if cleaned_value not in ["---", "-- ", "--- "] else None
                elif "%" in value:
                    return float(value.replace("%", "").strip())
                elif "V" in value:
                    # Check if value could be a version number
                    if "V" in value and any(c.isalpha() for c in value.replace("V", "")):
                        return value  # It's likely a version string, return as is
                    cleaned_value = value.replace("V", "").strip()
                    try:
                        return float(cleaned_value)
                    except ValueError:
                        return cleaned_value  # Return as string if not a valid float
                elif "RPM" in value:
                    return int(value.replace("RPM", "").strip())
                elif "kWh" in value:
                    return float(value.replace("kWh", "").strip())
                elif "kW" in value:
                    return float(value.replace("kW", "").strip())
                elif value.endswith("h") and self._attr_device_class == SensorDeviceClass.DURATION:
                    # Handle hour durations like '2266h'
                    return float(value.replace("h", "").strip())
                elif ":" in value and self._attr_device_class == SensorDeviceClass.DURATION:
                    # Handle time format HH:MM:SS or HH:MM
                    parts = value.split(":")
                    if len(parts) == 3:  # HH:MM:SS
                        hours = int(parts[0])
                        minutes = int(parts[1])
                        seconds = int(parts[2])
                        return hours + minutes/60 + seconds/3600
                    elif len(parts) == 2:  # HH:MM
                        hours = int(parts[0])
                        minutes = int(parts[1])
                        return hours + minutes/60

            return value
        except (ValueError, TypeError) as e:
            _LOGGER.warning(f"Error processing value '{value}' for {self._name}: {e}")
            return value  # Return the original string value if conversion fails
