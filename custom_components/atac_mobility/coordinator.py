"""Data update coordinator for ATAC Mobility."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from time import time

from aiohttp import ClientError
from google.transit import gtfs_realtime_pb2

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ALERT_MINUTES,
    CONF_LINE,
    CONF_SCAN_INTERVAL,
    CONF_STATIC_GTFS_URL,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    CONF_STOPS,
    CONF_TRIP_UPDATES_URL,
    CONF_VEHICLE_POSITIONS_URL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class StopConfig:
    """Configuration for one monitored stop."""

    stop_id: str
    stop_name: str
    alert_minutes: int


@dataclass(slots=True)
class VehicleSnapshot:
    """State snapshot for a running vehicle."""

    vehicle_id: str
    label: str | None
    route_id: str | None
    trip_id: str | None
    latitude: float
    longitude: float
    bearing: float | None
    speed: float | None
    timestamp: int | None


@dataclass(slots=True)
class StopSnapshot:
    """State snapshot for one monitored stop."""

    stop_id: str
    stop_name: str
    alert_minutes: int
    next_arrival_minutes: int | None
    next_arrival_unix: int | None
    trip_id: str | None


@dataclass(slots=True)
class CoordinatorData:
    """Coordinator payload."""

    vehicles: dict[int, VehicleSnapshot]
    stops: dict[str, StopSnapshot]


def _normalize_line(line: str | None) -> str:
    """Normalize line for loose matching."""
    return (line or "").strip().replace(" ", "").upper()


class RomaBusTrackerCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Fetch and filter GTFS realtime data by line."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self._line = entry.options.get(CONF_LINE, entry.data[CONF_LINE])
        self._trip_updates_url = entry.options.get(
            CONF_TRIP_UPDATES_URL, entry.data[CONF_TRIP_UPDATES_URL]
        )
        self._vehicle_positions_url = entry.options.get(
            CONF_VEHICLE_POSITIONS_URL, entry.data[CONF_VEHICLE_POSITIONS_URL]
        )
        self._static_gtfs_url = entry.options.get(
            CONF_STATIC_GTFS_URL, entry.data.get(CONF_STATIC_GTFS_URL)
        )
        interval_seconds = int(
            entry.options.get(CONF_SCAN_INTERVAL, entry.data[CONF_SCAN_INTERVAL])
        )

        raw_stops = entry.options.get(CONF_STOPS, entry.data.get(CONF_STOPS, []))
        self._stops = [
            StopConfig(
                stop_id=str(item.get(CONF_STOP_ID, "")).strip(),
                stop_name=str(item.get(CONF_STOP_NAME, "")).strip()
                or str(item.get(CONF_STOP_ID, "")).strip(),
                alert_minutes=int(item.get(CONF_ALERT_MINUTES, 5)),
            )
            for item in raw_stops
            if str(item.get(CONF_STOP_ID, "")).strip()
        ]

        self._session = async_get_clientsession(hass)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=max(5, interval_seconds)),
        )

    async def _fetch_feed(self, url: str) -> gtfs_realtime_pb2.FeedMessage:
        """Download and parse a GTFS protobuf feed."""
        try:
            async with self._session.get(url, timeout=15) as response:
                if response.status != 200:
                    raise UpdateFailed(
                        f"Failed to fetch {url} with status {response.status}"
                    )
                payload = await response.read()
        except ClientError as err:
            raise UpdateFailed(f"Network error fetching {url}: {err}") from err

        message = gtfs_realtime_pb2.FeedMessage()
        try:
            message.ParseFromString(payload)
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Invalid protobuf payload from {url}: {err}") from err

        return message

    async def _async_update_data(self) -> CoordinatorData:
        """Fetch latest GTFS feeds and keep vehicles for configured line."""
        trip_updates = await self._fetch_feed(self._trip_updates_url)
        vehicle_positions = await self._fetch_feed(self._vehicle_positions_url)

        selected_line = _normalize_line(self._line)
        now_unix = int(time())

        trip_to_route: dict[str, str] = {}
        next_by_stop: dict[str, tuple[int, str | None] | None] = {
            stop.stop_id: None for stop in self._stops
        }

        for entity in trip_updates.entity:
            if not entity.HasField("trip_update"):
                continue
            trip = entity.trip_update.trip
            if trip.trip_id and trip.route_id:
                trip_to_route[trip.trip_id] = trip.route_id

        for entity in trip_updates.entity:
            if not entity.HasField("trip_update"):
                continue

            trip_update = entity.trip_update
            trip = trip_update.trip
            route_id = trip.route_id or trip_to_route.get(trip.trip_id)
            if _normalize_line(route_id) != selected_line:
                continue

            for stop_time_update in trip_update.stop_time_update:
                stop_id = stop_time_update.stop_id
                if stop_id not in next_by_stop:
                    continue

                arrival_time = None
                if stop_time_update.HasField("arrival") and stop_time_update.arrival.time:
                    arrival_time = int(stop_time_update.arrival.time)
                elif (
                    stop_time_update.HasField("departure")
                    and stop_time_update.departure.time
                ):
                    arrival_time = int(stop_time_update.departure.time)

                if arrival_time is None or arrival_time < now_unix:
                    continue

                existing = next_by_stop[stop_id]
                if existing is None or arrival_time < existing[0]:
                    next_by_stop[stop_id] = (arrival_time, trip.trip_id or None)

        vehicles_by_id: dict[str, VehicleSnapshot] = {}
        for entity in vehicle_positions.entity:
            if not entity.HasField("vehicle"):
                continue

            vehicle = entity.vehicle
            trip = vehicle.trip
            position = vehicle.position

            route_id = trip.route_id or trip_to_route.get(trip.trip_id)
            if _normalize_line(route_id) != selected_line:
                continue

            if not position.latitude and not position.longitude:
                continue

            vehicle_id = vehicle.vehicle.id or vehicle.vehicle.label or entity.id
            if not vehicle_id:
                continue

            vehicles_by_id[vehicle_id] = VehicleSnapshot(
                vehicle_id=vehicle_id,
                label=vehicle.vehicle.label or None,
                route_id=route_id or None,
                trip_id=trip.trip_id or None,
                latitude=position.latitude,
                longitude=position.longitude,
                bearing=position.bearing if position.bearing else None,
                speed=position.speed if position.speed else None,
                timestamp=vehicle.timestamp if vehicle.timestamp else None,
            )

        vehicles: dict[int, VehicleSnapshot] = {}
        for index, vehicle_id in enumerate(sorted(vehicles_by_id), start=1):
            vehicles[index] = vehicles_by_id[vehicle_id]

        stops: dict[str, StopSnapshot] = {}
        for stop in self._stops:
            next_info = next_by_stop.get(stop.stop_id)
            next_arrival_unix: int | None = None
            next_arrival_minutes: int | None = None
            trip_id: str | None = None

            if next_info is not None:
                next_arrival_unix = next_info[0]
                trip_id = next_info[1]
                delta = max(0, next_arrival_unix - now_unix)
                next_arrival_minutes = delta // 60

            stops[stop.stop_id] = StopSnapshot(
                stop_id=stop.stop_id,
                stop_name=stop.stop_name,
                alert_minutes=stop.alert_minutes,
                next_arrival_minutes=next_arrival_minutes,
                next_arrival_unix=next_arrival_unix,
                trip_id=trip_id,
            )

        return CoordinatorData(vehicles=vehicles, stops=stops)
