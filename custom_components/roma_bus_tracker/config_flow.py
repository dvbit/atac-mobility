"""Config flow for ATAC Mobility."""

from __future__ import annotations

import csv
import io
import zipfile

from aiohttp import ClientError
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

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
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STATIC_GTFS_URL,
    DEFAULT_TRIP_UPDATES_URL,
    DEFAULT_VEHICLE_POSITIONS_URL,
    DOMAIN,
)


def _normalize_line(line: str | None) -> str:
    """Normalize line for loose matching."""
    return (line or "").strip().replace(" ", "").upper()


class RomaBusTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ATAC Mobility."""

    VERSION = 3

    def __init__(self) -> None:
        self._base_input: dict = {}
        self._stops: list[dict] = []
        self._line_stops: list[tuple[str, str]] | None = None
        self._line_options: list[tuple[str, str]] | None = None
        self._static_rows: dict[str, list[dict[str, str]]] | None = None

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle initial setup transport feeds and static GTFS source."""
        if user_input is not None:
            self._base_input = {
                CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                CONF_TRIP_UPDATES_URL: user_input[CONF_TRIP_UPDATES_URL],
                CONF_VEHICLE_POSITIONS_URL: user_input[CONF_VEHICLE_POSITIONS_URL],
                CONF_STATIC_GTFS_URL: user_input[CONF_STATIC_GTFS_URL],
            }
            return await self.async_step_line()

        schema = vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                    int, vol.Range(min=5, max=300)
                ),
                vol.Optional(
                    CONF_TRIP_UPDATES_URL, default=DEFAULT_TRIP_UPDATES_URL
                ): str,
                vol.Optional(
                    CONF_VEHICLE_POSITIONS_URL,
                    default=DEFAULT_VEHICLE_POSITIONS_URL,
                ): str,
                vol.Optional(CONF_STATIC_GTFS_URL, default=DEFAULT_STATIC_GTFS_URL): str,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_line(self, user_input: dict | None = None) -> FlowResult:
        """Select bus line from static GTFS descriptions."""
        errors: dict[str, str] = {}

        if self._line_options is None:
            self._line_options = await self._async_load_line_options()

        if not self._line_options:
            errors["base"] = "no_lines_found"

        if user_input is not None and not errors:
            line = user_input[CONF_LINE]
            await self.async_set_unique_id(_normalize_line(line))
            self._abort_if_unique_id_configured()

            self._base_input[CONF_LINE] = line
            self._stops = []
            return await self.async_step_stop_menu()

        options = [
            selector.SelectOptionDict(value=line_value, label=line_label)
            for line_value, line_label in self._line_options or []
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_LINE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )

        return self.async_show_form(step_id="line", data_schema=schema, errors=errors)

    async def async_step_stop_menu(self, user_input: dict | None = None) -> FlowResult:
        """Stop selection actions: add or finish."""
        if self._line_stops is None:
            self._line_stops = await self._async_load_line_stops()

        selected_ids = {item[CONF_STOP_ID] for item in self._stops}
        selected_names = [item[CONF_STOP_NAME] for item in self._stops]
        selected_text = ", ".join(selected_names) if selected_names else "-"

        remaining = [stop for stop in (self._line_stops or []) if stop[0] not in selected_ids]

        if not self._line_stops:
            return self.async_show_menu(
                step_id="stop_menu",
                menu_options=["stop_finish"],
                description_placeholders={
                    "count": str(len(self._stops)),
                    "selected": selected_text,
                },
            )

        menu_options = ["stop_finish"]
        if remaining:
            menu_options.insert(0, "add_stop")

        return self.async_show_menu(
            step_id="stop_menu",
            menu_options=menu_options,
            description_placeholders={
                "count": str(len(self._stops)),
                "selected": selected_text,
            },
        )

    async def async_step_add_stop(self, user_input: dict | None = None) -> FlowResult:
        """Select one monitored stop from dropdown and alert threshold."""
        if self._line_stops is None:
            self._line_stops = await self._async_load_line_stops()

        selected_ids = {item[CONF_STOP_ID] for item in self._stops}
        available_stops = [
            (stop_id, stop_name)
            for stop_id, stop_name in (self._line_stops or [])
            if stop_id not in selected_ids
        ]

        if not available_stops:
            return await self.async_step_stop_menu()

        if user_input is not None:
            selected_stop_id = user_input[CONF_STOP_ID]
            selected_stop_name = next(
                (
                    stop_name
                    for stop_id, stop_name in available_stops
                    if stop_id == selected_stop_id
                ),
                selected_stop_id,
            )

            self._stops.append(
                {
                    CONF_STOP_ID: selected_stop_id,
                    CONF_STOP_NAME: selected_stop_name,
                    CONF_ALERT_MINUTES: user_input[CONF_ALERT_MINUTES],
                }
            )
            return await self.async_step_stop_menu()

        options = [
            selector.SelectOptionDict(value=stop_id, label=f"{stop_name} ({stop_id})")
            for stop_id, stop_name in available_stops
        ]

        schema = vol.Schema(
            {
                vol.Required(CONF_STOP_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_ALERT_MINUTES, default=5): vol.All(
                    int, vol.Range(min=1, max=120)
                ),
            }
        )

        return self.async_show_form(
            step_id="add_stop",
            data_schema=schema,
            description_placeholders={"count": str(len(self._stops))},
        )

    async def async_step_stop_finish(self, user_input: dict | None = None) -> FlowResult:
        """Finish setup with selected stops."""
        return self._create_entry()

    def _create_entry(self) -> FlowResult:
        """Create config entry."""
        line = self._base_input[CONF_LINE]
        return self.async_create_entry(
            title=f"ATAC Mobility {line}",
            data={**self._base_input, CONF_STOPS: self._stops},
        )

    async def _async_load_line_options(self) -> list[tuple[str, str]]:
        """Load bus lines from static GTFS for line picker."""
        rows = await self._async_get_static_rows()
        routes_rows = rows.get("routes", [])

        options: dict[str, str] = {}
        for row in routes_rows:
            route_id = (row.get("route_id") or "").strip()
            short_name = (row.get("route_short_name") or "").strip()
            long_name = (row.get("route_long_name") or "").strip()
            route_desc = (row.get("route_desc") or "").strip()

            line_value = short_name or route_id
            if not line_value:
                continue

            detail = long_name or route_desc
            label = f"{line_value} - {detail}" if detail else line_value
            options.setdefault(line_value, label)

        return sorted(options.items(), key=lambda item: item[1].upper())

    async def _async_load_line_stops(self) -> list[tuple[str, str]]:
        """Load unique stops served by the configured line from static GTFS."""
        rows = await self._async_get_static_rows()
        routes_rows = rows.get("routes", [])
        trips_rows = rows.get("trips", [])
        stop_times_rows = rows.get("stop_times", [])
        stops_rows = rows.get("stops", [])

        line = _normalize_line(self._base_input[CONF_LINE])

        route_ids: set[str] = set()
        for row in routes_rows:
            short_name = _normalize_line(row.get("route_short_name"))
            route_id = _normalize_line(row.get("route_id"))
            if short_name == line or route_id == line:
                raw_route_id = (row.get("route_id") or "").strip()
                if raw_route_id:
                    route_ids.add(raw_route_id)

        if not route_ids:
            return []

        trip_ids: set[str] = set()
        for row in trips_rows:
            route_id = (row.get("route_id") or "").strip()
            trip_id = (row.get("trip_id") or "").strip()
            if route_id in route_ids and trip_id:
                trip_ids.add(trip_id)

        if not trip_ids:
            return []

        stop_ids: set[str] = set()
        for row in stop_times_rows:
            trip_id = (row.get("trip_id") or "").strip()
            stop_id = (row.get("stop_id") or "").strip()
            if trip_id in trip_ids and stop_id:
                stop_ids.add(stop_id)

        if not stop_ids:
            return []

        stop_names: dict[str, str] = {}
        for row in stops_rows:
            stop_id = (row.get("stop_id") or "").strip()
            if stop_id not in stop_ids:
                continue
            stop_name = (row.get("stop_name") or row.get("stop_desc") or "").strip()
            if stop_name:
                stop_names[stop_id] = stop_name

        pairs = [(stop_id, stop_names.get(stop_id, stop_id)) for stop_id in stop_ids]
        return sorted(pairs, key=lambda item: item[1].upper())

    async def _async_get_static_rows(self) -> dict[str, list[dict[str, str]]]:
        """Download static GTFS once and return required CSV rows."""
        if self._static_rows is not None:
            return self._static_rows

        url = self._base_input.get(CONF_STATIC_GTFS_URL, DEFAULT_STATIC_GTFS_URL)
        session = async_get_clientsession(self.hass)

        try:
            async with session.get(url, timeout=20) as response:
                if response.status != 200:
                    self._static_rows = {}
                    return self._static_rows
                payload = await response.read()
        except ClientError:
            self._static_rows = {}
            return self._static_rows

        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                self._static_rows = {
                    "routes": self._read_csv_rows(archive, "routes.txt"),
                    "trips": self._read_csv_rows(archive, "trips.txt"),
                    "stop_times": self._read_csv_rows(archive, "stop_times.txt"),
                    "stops": self._read_csv_rows(archive, "stops.txt"),
                }
        except Exception:  # noqa: BLE001
            self._static_rows = {}

        return self._static_rows

    @staticmethod
    def _read_csv_rows(archive: zipfile.ZipFile, filename: str) -> list[dict[str, str]]:
        """Read a CSV file from zip into dict rows."""
        with archive.open(filename) as file_handle:
            raw = file_handle.read().decode("utf-8-sig", errors="replace")
        return list(csv.DictReader(io.StringIO(raw)))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Create the options flow."""
        return RomaBusTrackerOptionsFlow(config_entry)


class RomaBusTrackerOptionsFlow(config_entries.OptionsFlow):
    """Options flow for ATAC Mobility."""

    def __init__(self, config_entry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        """Manage integration options."""
        if user_input is not None:
            existing_stops = self._config_entry.options.get(
                CONF_STOPS,
                self._config_entry.data.get(CONF_STOPS, []),
            )
            user_input[CONF_STOPS] = existing_stops
            return self.async_create_entry(title="", data=user_input)

        line = self._config_entry.options.get(
            CONF_LINE,
            self._config_entry.data.get(CONF_LINE),
        )
        scan_interval = self._config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self._config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        trip_updates_url = self._config_entry.options.get(
            CONF_TRIP_UPDATES_URL,
            self._config_entry.data.get(CONF_TRIP_UPDATES_URL, DEFAULT_TRIP_UPDATES_URL),
        )
        vehicle_positions_url = self._config_entry.options.get(
            CONF_VEHICLE_POSITIONS_URL,
            self._config_entry.data.get(
                CONF_VEHICLE_POSITIONS_URL,
                DEFAULT_VEHICLE_POSITIONS_URL,
            ),
        )
        static_gtfs_url = self._config_entry.options.get(
            CONF_STATIC_GTFS_URL,
            self._config_entry.data.get(CONF_STATIC_GTFS_URL, DEFAULT_STATIC_GTFS_URL),
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_LINE, default=line): str,
                vol.Required(CONF_SCAN_INTERVAL, default=scan_interval): vol.All(
                    int, vol.Range(min=5, max=300)
                ),
                vol.Required(CONF_TRIP_UPDATES_URL, default=trip_updates_url): str,
                vol.Required(
                    CONF_VEHICLE_POSITIONS_URL,
                    default=vehicle_positions_url,
                ): str,
                vol.Required(CONF_STATIC_GTFS_URL, default=static_gtfs_url): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
