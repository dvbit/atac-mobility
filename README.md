# ATAC Mobility

Home Assistant custom integration for ATAC/Roma mobility using GTFS Realtime feeds.

## Features

- Track active buses for a selected line as device trackers.
- Optional stop monitoring with binary sensors and arrival threshold alerts.
- Config flow with line and stop selection from static GTFS data.
- Italian and English localization.

## Installation (HACS)

1. Open HACS in Home Assistant.
2. Add this repository as a **Custom repository** with category **Integration**.
3. Install **ATAC Mobility**.
4. Restart Home Assistant.
5. Go to **Settings -> Devices & Services -> Add Integration** and add **ATAC Mobility**.

## Configuration flow

1. Set feed URLs and update interval.
2. Select the ATAC line from the static GTFS catalog.
3. Optionally add monitored stops and finish setup.

## Data sources (defaults)

- Trip updates: `https://romamobilita.it/sites/default/files/rome_rtgtfs_trip_updates_feed.pb`
- Vehicle positions: `https://romamobilita.it/sites/default/files/rome_rtgtfs_vehicle_positions_feed.pb`
- Static GTFS: `https://romamobilita.it/sites/default/files/rome_static_gtfs.zip`

## Domain

`roma_bus_tracker`
