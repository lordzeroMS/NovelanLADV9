from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory

from .const import CONF_IP_ADDRESS, CONF_PIN, DOMAIN
from .reading_data import ControlCommandError, fetch_controls, set_control


@dataclass(slots=True)
class ControlMeta:
    name: str
    options: list[tuple[str, str]]  # (value, label)
    values_id: str | None
    navigation_id: str | None


async def async_setup_entry(hass, config_entry, async_add_entities):
    ip = config_entry.data.get(CONF_IP_ADDRESS)
    pin = config_entry.data.get(CONF_PIN, "999999")
    raw_controls = await fetch_controls(ip, pin)

    entities: list[NovelanLADV9SelectEntity] = []
    for control in raw_controls:
        name = control.get("name")
        if not name:
            continue
        options = control.get("options") or control.get("option")
        if isinstance(options, dict):
            options = [options]
        labels: list[tuple[str, str]] = []
        for opt in options or []:
            if isinstance(opt, dict):
                labels.append((str(opt.get("value")), opt.get("label") or opt.get("#text") or ""))
        meta = ControlMeta(
            name=name,
            options=labels,
            values_id=control.get("values_id") or control.get("@id"),
            navigation_id=control.get("page_id") or control.get("navigation_id"),
        )
        entities.append(NovelanLADV9SelectEntity(ip, pin, meta, control.get("value")))

    async_add_entities(entities)


class NovelanLADV9SelectEntity(SelectEntity):
    def __init__(self, ip: str, pin: str, meta: ControlMeta, current_value: str) -> None:
        self._ip = ip
        self._pin = pin
        self._meta = meta
        self._value = current_value

        self._attr_name = meta.name
        self._attr_options = [label for _, label in meta.options]
        ip_id = ip.replace('.', '_')
        slug = meta.name.lower().replace(' ', '_')
        self._attr_unique_id = f"{DOMAIN}_{ip_id}_{slug}"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info = {
            "identifiers": {(DOMAIN, ip)},
            "name": f"Novelan LADV9 ({ip})",
            "manufacturer": "Novelan",
            "model": "LADV9",
        }

    @property
    def current_option(self) -> str | None:
        return self._value

    async def async_select_option(self, option: str) -> None:
        try:
            value = next(val for val, label in self._meta.options if label == option)
        except StopIteration as err:
            raise HomeAssistantError(f"Option '{option}' not available for {self._attr_name}") from err

        if self._meta.values_id is None:
            raise HomeAssistantError(f"Control {self._attr_name} does not expose an id")

        try:
            await set_control(
                self._ip,
                self._pin,
                control_id=self._meta.values_id,
                value=value,
                page_id=self._meta.navigation_id,
                label=self._meta.name,
            )
        except ControlCommandError as err:
            raise HomeAssistantError(
                f"Failed to set {self._attr_name} to {option}: {err}"
            ) from err

        self._value = option
        self.async_write_ha_state()

    async def async_update(self) -> None:
        controls = await fetch_controls(self._ip, self._pin)
        for control in controls:
            if control.get("name") == self._meta.name:
                self._value = control.get("value")
                self._meta.values_id = control.get("values_id") or control.get("@id")
                self._meta.navigation_id = control.get("page_id") or control.get("navigation_id")
                break
