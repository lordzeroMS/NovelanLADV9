import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    LOGGER.info("Setting up Novelan LADV9 integration")
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "select", "number"])
    return True
