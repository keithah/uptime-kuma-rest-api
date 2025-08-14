# Uptime Kuma API Examples

This directory contains example scripts demonstrating how to use the Uptime Kuma Socket.io API directly for advanced operations.

## Prerequisites

Make sure you have the required dependencies installed:
```bash
pip install python-socketio[client]
```

Set your environment variables:
```bash
export UPTIME_KUMA_URL="https://your-uptime-kuma-server"
export UPTIME_KUMA_USERNAME="your-username"
export UPTIME_KUMA_PASSWORD="your-password"
```

## Available Examples

### list_monitors.py
Lists all monitors organized by groups, showing their current configuration.

```bash
python list_monitors.py
```

### bulk_update_by_group.py
Updates all monitors within a specific group with new settings.

```bash
python bulk_update_by_group.py "Group Name"
```

Example:
```bash
python bulk_update_by_group.py "Media Playback"
```

This will update all monitors in the "Media Playback" group with:
- Interval: 180 seconds (3 minutes)
- Retry Interval: 30 seconds
- Max Retries: 3

## Note

These scripts use Uptime Kuma's internal Socket.io API which is not officially documented or supported. The API may change in future versions of Uptime Kuma.