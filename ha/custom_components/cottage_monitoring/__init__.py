from datetime import timedelta

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .nord_client import NordClient

try:
    from homeassistant.const import Platform
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import discovery
    from homeassistant.helpers.aiohttp_client import async_get_clientsession
    from homeassistant.helpers.typing import ConfigType

    from .coordinator import CottageCoordinator
    from .transport import AiohttpTransport
except ImportError:
    # pytest without Home Assistant / aiohttp still imports nord_client + snapshot.
    pass
else:
    PLATFORMS = (
        Platform.LIGHT,
        Platform.CLIMATE,
        Platform.SENSOR,
        Platform.BINARY_SENSOR,
        Platform.SWITCH,
        Platform.WATER_HEATER,
    )

    async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
        conf = config.get(DOMAIN)
        if conf is None:
            return True
        session = async_get_clientsession(hass)
        client = NordClient(
            str(conf["base_url"]),
            str(conf["api_key"]),
            str(conf["house_id"]),
            transport=AiohttpTransport(session),
        )
        coordinator = CottageCoordinator(
            hass,
            client,
            update_interval=timedelta(
                seconds=int(conf.get("scan_interval", DEFAULT_SCAN_INTERVAL))
            ),
        )
        await coordinator.async_refresh()
        hass.data[DOMAIN] = {"coordinator": coordinator, "config": conf}
        for platform in PLATFORMS:
            hass.async_create_task(
                discovery.async_load_platform(hass, platform, DOMAIN, {}, config)
            )
        return True
