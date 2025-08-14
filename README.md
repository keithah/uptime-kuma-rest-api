# Uptime Kuma REST API Wrapper

A Flask-based REST API wrapper for Uptime Kuma's Socket.io API, enabling programmatic monitor creation and management via HTTP endpoints.

## Features

- **HTTP REST API** for Uptime Kuma monitor management
- **Bulk monitor creation** - create multiple monitors at once
- **Bulk monitor updates** - update multiple monitors using Socket.io directly
- **Monitor listing and grouping** - retrieve and filter monitors by group
- **Automatic authentication** using Socket.io callbacks
- **Environment variable configuration**
- **Real-time connection status** monitoring

## Installation

1. Clone the repository:
```bash
git clone https://github.com/your-username/uptime-kuma-rest-api.git
cd uptime-kuma-rest-api
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment variables:
```bash
export UPTIME_KUMA_URL="http://your-uptime-kuma-server:3001"
export UPTIME_KUMA_USERNAME="your-username"
export UPTIME_KUMA_PASSWORD="your-password"
```

4. Run the API wrapper:
```bash
python uptime_kuma_rest_api.py
```

The API will be available at `http://127.0.0.1:5001`

## API Endpoints

### Health Check
```bash
GET /health
```
Returns connection and authentication status.

### Create Single Monitor
```bash
POST /monitors
Content-Type: application/json

{
  "name": "My Website",
  "url": "https://example.com",
  "description": "Monitor my website"
}
```

### Create Multiple Monitors
```bash
POST /monitors/bulk
Content-Type: application/json

[
  {
    "name": "Website 1",
    "url": "https://example1.com"
  },
  {
    "name": "Website 2", 
    "url": "https://example2.com"
  }
]
```

### Reconnect
```bash
POST /connect
```
Manually reconnect and authenticate to Uptime Kuma.

## Configuration

Configure the API using environment variables:

- `UPTIME_KUMA_URL` - Your Uptime Kuma server URL (default: `http://localhost:3001`)
- `UPTIME_KUMA_USERNAME` - Username for authentication (default: `admin`)
- `UPTIME_KUMA_PASSWORD` - Password for authentication (default: `admin`)

## Monitor Defaults

The API automatically sets sensible defaults for HTTP monitors:

- **Type**: `http`
- **Method**: `GET`
- **Interval**: `300` seconds (5 minutes)
- **Max Retries**: `3`
- **Retry Interval**: `60` seconds
- **Timeout**: `30` seconds
- **Active**: `true`
- **Accepted Status Codes**: `["200-299"]`

You can override any of these by including them in your request.

## Example Usage

Create a website monitor:
```bash
curl -X POST http://127.0.0.1:5001/monitors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Blog",
    "url": "https://myblog.com",
    "description": "Monitor my personal blog",
    "interval": 60
  }'
```

Create multiple monitors at once:
```bash
curl -X POST http://127.0.0.1:5001/monitors/bulk \
  -H "Content-Type: application/json" \
  -d '[
    {
      "name": "API Server",
      "url": "https://api.example.com/health"
    },
    {
      "name": "Web App",
      "url": "https://app.example.com"
    }
  ]'
```

## Requirements

- Python 3.7+
- Uptime Kuma server with authentication enabled
- Network access to your Uptime Kuma instance

## Advanced Usage - Direct Socket.io Operations

While the REST API wrapper provides HTTP endpoints for monitor creation, you can also use Python scripts to directly interact with Uptime Kuma's Socket.io API for more advanced operations like bulk updates.

### Bulk Update Monitors by Group

```python
#!/usr/bin/env python3
import socketio
import time
import os

# Configuration from environment
UPTIME_KUMA_URL = os.getenv("UPTIME_KUMA_URL")
USERNAME = os.getenv("UPTIME_KUMA_USERNAME")
PASSWORD = os.getenv("UPTIME_KUMA_PASSWORD")

sio = socketio.Client()

# Connect and authenticate
sio.connect(UPTIME_KUMA_URL)
sio.emit('login', {
    'username': USERNAME,
    'password': PASSWORD,
    'token': ''
}, callback=lambda r: print("Authenticated" if r.get('ok') else "Auth failed"))

# Listen for monitor list
@sio.on('monitorList')
def on_monitor_list(data):
    # Find monitors in a specific group
    for monitor_id, monitor in data.items():
        if monitor.get('parent') == GROUP_ID:  # Replace GROUP_ID
            # Update monitor settings
            monitor['interval'] = 180
            monitor['retryInterval'] = 30
            monitor['maxretries'] = 3
            sio.emit('editMonitor', monitor)

# Wait for operations to complete
time.sleep(5)
sio.disconnect()
```

### List All Monitors

```python
@sio.on('monitorList')
def on_monitor_list(data):
    for monitor_id, monitor in data.items():
        print(f"{monitor['name']} (ID: {monitor['id']}, Type: {monitor['type']})")
```

## Limitations

- REST API currently supports HTTP monitor creation only
- Direct Socket.io operations require understanding of Uptime Kuma's internal API
- Uses Uptime Kuma's internal Socket.io API (not officially supported)
- API may break with future Uptime Kuma updates

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## Disclaimer

This project uses Uptime Kuma's internal Socket.io API which is not officially supported for third-party integrations. Use at your own risk and expect potential breaking changes with Uptime Kuma updates.