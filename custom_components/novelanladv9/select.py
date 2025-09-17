from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from .reading_data import ControlCommandError, fetch_controls, set_control
from .const import CONF_IP_ADDRESS, CONF_PIN, DOMAIN


async def async_setup_entry(hass, config_entry, async_add_entities):
    ip = config_entry.data.get(CONF_IP_ADDRESS)
    pin = config_entry.data.get(CONF_PIN, "999999")
    controls = await fetch_controls(ip, pin)
    entities = []
    for control in controls:
        entities.append(NovelanLADV9SelectEntity(ip, pin, control))
    async_add_entities(entities)

class NovelanLADV9SelectEntity(SelectEntity):
    def __init__(self, ip, pin, control):
        self._ip = ip
        self._pin = pin
        self._control = control
        # Normalize name
        name = control.get("name")
        if isinstance(name, list):
            name = name[0]
        self._attr_name = name
        # Options
        options = control.get("option")
        if isinstance(options, dict):
            options = [options]
        self._attr_options = [opt.get("#text") for opt in options]
        # Keep control id for SET operations; it's ephemeral per session
        self._control_id = control.get("@id")
        # Stable unique_id based on ip + logical name
        ip_id = ip.replace('.', '_')
        slug = (
            str(name).lower()
            .replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
            .replace("ß", "ss").replace(".", "").replace(" ", "_")
        )
        self._attr_unique_id = f"{DOMAIN}_{ip_id}_{slug}"
        self._attr_entity_category = EntityCategory.CONFIG
        self._value = control["value"]
        self._attr_device_info = {
            "identifiers": {(DOMAIN, ip)},
            "name": f"Novelan LADV9 ({ip})",
            "manufacturer": "Novelan",
            "model": "LADV9",
        }

    @property
    def current_option(self):
        return self._value

    async def async_select_option(self, option: str):
        # Find the value corresponding to the selected option text
        value = None
        opts = self._control.get("option")
        if isinstance(opts, dict):
            opts = [opts]
        for opt in opts:
            if opt["#text"] == option:
                value = opt["@value"]
                break
        if value is not None:
            try:
                await set_control(self._ip, self._pin, self._control_id, value)
            except ControlCommandError as err:
                raise HomeAssistantError(
                    f"Failed to set {self._attr_name} to {option}: {err}"
                ) from err
            self._value = option
            self.async_write_ha_state()

    async def async_update(self):
        controls = await fetch_controls(self._ip, self._pin)
        for control in controls:
            if control.get("@id") == self._control_id:
                self._value = control["value"]
                break
