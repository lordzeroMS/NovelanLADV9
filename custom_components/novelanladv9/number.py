from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberDeviceClass
from homeassistant.const import UnitOfTemperature
from .const import DOMAIN, CONF_IP_ADDRESS, CONF_PIN
from .reading_data import fetch_setpoints, set_control


LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    ip_address = entry.data[CONF_IP_ADDRESS]
    pin = entry.data.get(CONF_PIN, "999999")

    setpoints = await fetch_setpoints(ip_address, pin)

    entities: list[NumberEntity] = []

    # Warmwasser-Soll (hot water setpoint)
    ww = setpoints.get("Warmwasser-Soll")
    if ww:
        max_ww = setpoints.get("Max.Warmwassertemp.")
        max_val = _parse_temp(max_ww["value"]) if max_ww else 65.0
        entities.append(
            LuxWsNumber(
                ip_address,
                pin,
                control_id=ww["id"],
                name="Warmwasser-Soll",
                unit=UnitOfTemperature.CELSIUS,
                device_class=NumberDeviceClass.TEMPERATURE,
                min_value=20.0,
                max_value=max_val,
                step=0.5,
            )
        )

    # Rückl.-Begr. (return temp limit)
    rl = setpoints.get("Rückl.-Begr.")
    if rl:
        entities.append(
            LuxWsNumber(
                ip_address,
                pin,
                control_id=rl["id"],
                name="Rückl.-Begr.",
                unit=UnitOfTemperature.CELSIUS,
                device_class=NumberDeviceClass.TEMPERATURE,
                min_value=10.0,
                max_value=70.0,
                step=0.5,
            )
        )

    if entities:
        async_add_entities(entities)


def _parse_temp(v: str | None) -> float | None:
    if not v:
        return None
    s = str(v)
    for suf in ["°C", "C", "K", "°K"]:
        if s.endswith(suf):
            s = s.replace(suf, "").strip()
            break
    try:
        return float(s)
    except Exception:
        return None


class LuxWsNumber(NumberEntity):
    def __init__(
        self,
        ip: str,
        pin: str,
        control_id: str,
        name: str,
        unit: str,
        device_class: NumberDeviceClass,
        min_value: float,
        max_value: float,
        step: float,
    ) -> None:
        self._ip = ip
        self._pin = pin
        self._control_id = control_id
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_step = step
        self._attr_should_poll = True
        # Stable unique_id per ip + logical name
        ip_id = ip.replace('.', '_')
        slug = (
            name.lower()
            .replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
            .replace("ß", "ss").replace(".", "").replace(" ", "_")
        )
        self._attr_unique_id = f"{DOMAIN}_{ip_id}_{slug}"
        self._value = None
        self._attr_device_info = {
            "identifiers": {(DOMAIN, ip)},
            "name": f"Novelan LADV9 ({ip})",
            "manufacturer": "Novelan",
            "model": "LADV9",
        }

    @property
    def native_value(self):
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        # round to step and format with one decimal
        step = self._attr_native_step or 0.5
        rounded = round(value / step) * step
        payload = f"{rounded:.1f}".rstrip("0").rstrip(".")
        await set_control(self._ip, self._pin, self._control_id, payload)
        self._value = rounded
        self.async_write_ha_state()
        try:
            await self.async_update()
        except Exception as err:  # pragma: no cover - refresh best effort
            LOGGER.debug(
                "Failed to refresh %s after setting value: %s",
                self.entity_id,
                err,
            )
            return
        self.async_write_ha_state()

    async def async_update(self) -> None:
        # Re-fetch current setpoints and update our value
        sp = await fetch_setpoints(self._ip, self._pin)
        entry = sp.get(self._attr_name)
        if entry and entry.get("value") is not None:
            parsed = _parse_temp(entry["value"])
            if parsed is not None:
                self._value = parsed
