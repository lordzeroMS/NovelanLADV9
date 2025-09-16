from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import EntityCategory
from .reading_data import fetch_controls, set_control
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
        self._attr_name = control["name"]
        options = control.get("option")
        if isinstance(options, dict):
            options = [options]
        self._attr_options = [opt.get("#text") for opt in options]
        self._attr_unique_id = control["@id"]
        self._attr_entity_category = EntityCategory.CONFIG
        self._value = control["value"]

    @property
    def current_option(self):
        return self._value

    async def async_select_option(self, option: str):
        # Find the value corresponding to the selected option text
        value = None
        for opt in self._control["option"]:
            if opt["#text"] == option:
                value = opt["@value"]
                break
        if value is not None:
            await set_control(self._ip, self._pin, self._attr_unique_id, value)
            self._value = option
            self.async_write_ha_state()

    async def async_update(self):
        controls = await fetch_controls(self._ip, self._pin)
        for control in controls:
            if control["@id"] == self._attr_unique_id:
                self._value = control["value"]
                break
