"""Device tracker platform for ATAC Mobility."""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_LINE, DOMAIN
from .coordinator import CoordinatorData, RomaBusTrackerCoordinator, VehicleSnapshot


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Roma bus trackers from config entry."""
    coordinator: RomaBusTrackerCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: dict[int, RomaBusDeviceTracker] = {}

    def _sync_entities() -> None:
        new_entities: list[RomaBusDeviceTracker] = []
        for bus_number in coordinator.data.vehicles:
            if bus_number in entities:
                continue
            entity = RomaBusDeviceTracker(coordinator, entry, bus_number)
            entities[bus_number] = entity
            new_entities.append(entity)

        if new_entities:
            async_add_entities(new_entities)

    _sync_entities()

    def _handle_coordinator_update() -> None:
        _sync_entities()

    unsub = coordinator.async_add_listener(_handle_coordinator_update)
    entry.async_on_unload(unsub)


class RomaBusDeviceTracker(CoordinatorEntity[RomaBusTrackerCoordinator], TrackerEntity):
    """Represent one running bus slot as a tracker entity."""

    _attr_should_poll = False
    _attr_icon = "mdi:bus"

    def __init__(
        self,
        coordinator: RomaBusTrackerCoordinator,
        entry: ConfigEntry,
        bus_number: int,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._bus_number = bus_number

        line = entry.options.get(CONF_LINE, entry.data[CONF_LINE])
        self._attr_unique_id = f"{entry.entry_id}_bus_{bus_number}"
        self._attr_name = None
        self._attr_translation_key = "bus_tracker"
        self._attr_translation_placeholders = {
            "number": str(bus_number),
            "line": line,
        }
        self._attr_extra_state_attributes = {"line": line}

    @property
    def source_type(self) -> SourceType:
        """Return source type."""
        return SourceType.GPS

    @property
    def _vehicle(self) -> VehicleSnapshot | None:
        """Return current vehicle snapshot if available."""
        data: CoordinatorData = self.coordinator.data
        return data.vehicles.get(self._bus_number)

    @property
    def available(self) -> bool:
        """Return true if this bus slot is active."""
        return self._vehicle is not None and super().available

    @property
    def latitude(self) -> float | None:
        """Return latitude."""
        vehicle = self._vehicle
        return vehicle.latitude if vehicle else None

    @property
    def longitude(self) -> float | None:
        """Return longitude."""
        vehicle = self._vehicle
        return vehicle.longitude if vehicle else None

    @property
    def location_accuracy(self) -> int:
        """Return rough location accuracy in meters."""
        return 20

    @property
    def extra_state_attributes(self) -> dict[str, str | float | int | None]:
        """Return additional data for the tracked bus."""
        vehicle = self._vehicle
        line = self._entry.options.get(CONF_LINE, self._entry.data[CONF_LINE])
        if vehicle is None:
            return {"line": line}

        return {
            "line": line,
            "vehicle_id": vehicle.vehicle_id,
            "route_id": vehicle.route_id,
            "trip_id": vehicle.trip_id,
            "vehicle_label": vehicle.label,
            "speed_mps": vehicle.speed,
            "bearing": vehicle.bearing,
            "timestamp": vehicle.timestamp,
        }
