"""ATAC Mobility integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_STATIC_GTFS_URL, CONF_STOPS, DEFAULT_STATIC_GTFS_URL, DOMAIN, PLATFORMS
from .coordinator import RomaBusTrackerCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ATAC Mobility from a config entry."""
    coordinator = RomaBusTrackerCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries."""
    if entry.version == 1:
        data = {
            **entry.data,
            CONF_STOPS: entry.data.get(CONF_STOPS, []),
            CONF_STATIC_GTFS_URL: entry.data.get(
                CONF_STATIC_GTFS_URL, DEFAULT_STATIC_GTFS_URL
            ),
        }
        hass.config_entries.async_update_entry(entry, data=data, version=3)
        return True
    if entry.version == 2:
        data = {
            **entry.data,
            CONF_STATIC_GTFS_URL: entry.data.get(
                CONF_STATIC_GTFS_URL, DEFAULT_STATIC_GTFS_URL
            ),
        }
        hass.config_entries.async_update_entry(entry, data=data, version=3)
    return True
