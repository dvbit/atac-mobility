"""Constants for ATAC Mobility."""

DOMAIN = "roma_bus_tracker"

CONF_LINE = "line"
CONF_TRIP_UPDATES_URL = "trip_updates_url"
CONF_VEHICLE_POSITIONS_URL = "vehicle_positions_url"
CONF_STATIC_GTFS_URL = "static_gtfs_url"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_MONITOR_STOPS = "monitor_stops"
CONF_STOP_COUNT = "stop_count"
CONF_STOPS = "stops"
CONF_STOP_ID = "stop_id"
CONF_STOP_NAME = "stop_name"
CONF_ALERT_MINUTES = "alert_minutes"

DEFAULT_SCAN_INTERVAL = 30
DEFAULT_TRIP_UPDATES_URL = (
    "https://romamobilita.it/sites/default/files/rome_rtgtfs_trip_updates_feed.pb"
)
DEFAULT_VEHICLE_POSITIONS_URL = (
    "https://romamobilita.it/sites/default/files/rome_rtgtfs_vehicle_positions_feed.pb"
)
DEFAULT_STATIC_GTFS_URL = "https://romamobilita.it/sites/default/files/rome_static_gtfs.zip"

PLATFORMS = ["device_tracker", "binary_sensor"]
