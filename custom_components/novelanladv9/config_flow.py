import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN, CONF_IP_ADDRESS, CONF_PIN

class LueftungsanlageConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return LueftungsanlageOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title=f"Novelan LADV9 ({user_input[CONF_IP_ADDRESS]})",
                data=user_input
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_IP_ADDRESS): str,
                vol.Required(CONF_PIN, default="999999"): str
            })
        )

class LueftungsanlageOptionsFlowHandler(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_IP_ADDRESS, default=self.config_entry.data.get(CONF_IP_ADDRESS)): str,
                vol.Required(CONF_PIN, default=self.config_entry.data.get(CONF_PIN, "999999")): str
            })
        )