"""Binary sensors for monitored Roma bus stops."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CoordinatorData, RomaBusTrackerCoordinator, StopSnapshot


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up monitored stop sensors."""
    coordinator: RomaBusTrackerCoordinator = hass.data[DOMAIN][entry.entry_id]
    sensors = [
        RomaBusStopBinarySensor(
            coordinator,
            entry,
            stop_id,
            coordinator.data.stops[stop_id].stop_name,
        )
        for stop_id in coordinator.data.stops
    ]
    if sensors:
        async_add_entities(sensors)


class RomaBusStopBinarySensor(CoordinatorEntity[RomaBusTrackerCoordinator], BinarySensorEntity):
    """Binary sensor for one monitored stop."""

    _attr_should_poll = False
    _attr_icon = "mdi:bus-stop-covered"

    def __init__(
        self,
        coordinator: RomaBusTrackerCoordinator,
        entry: ConfigEntry,
        stop_id: str,
        stop_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._stop_id = stop_id
        self._stop_name = stop_name
        self._attr_unique_id = f"{entry.entry_id}_stop_{stop_id}"
        self._attr_name = None
        self._attr_translation_key = "stop_monitor"
        self._attr_translation_placeholders = {"stop_name": self._stop_name}

    @property
    def _stop(self) -> StopSnapshot | None:
        """Return current stop snapshot if available."""
        data: CoordinatorData = self.coordinator.data
        return data.stops.get(self._stop_id)

    @property
    def available(self) -> bool:
        """Return true if stop is available."""
        return self._stop is not None and super().available

    @property
    def is_on(self) -> bool:
        """Return true when next arrival is within threshold."""
        stop = self._stop
        if stop is None or stop.next_arrival_minutes is None:
            return False
        return stop.next_arrival_minutes <= stop.alert_minutes

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        """Return stop timing details."""
        stop = self._stop
        if stop is None:
            return {"stop_id": self._stop_id}

        return {
            "stop_id": stop.stop_id,
            "stop_name": stop.stop_name,
            "arrival_alert_minutes": stop.alert_minutes,
            "next_arrival_minutes": stop.next_arrival_minutes,
            "next_arrival_unix": stop.next_arrival_unix,
            "trip_id": stop.trip_id,
        }
