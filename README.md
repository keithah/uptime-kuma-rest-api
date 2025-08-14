# Uptime Kuma REST API Wrapper

A comprehensive REST API wrapper for Uptime Kuma's Socket.io API, enabling full monitor and notification management via simple HTTP endpoints and curl commands.

## Features

- **Complete REST API** for Uptime Kuma management
- **Monitor Operations**: Create, list, update, pause, resume, delete
- **Bulk Operations**: Update, control, and manage multiple monitors at once
- **Notification Management**: Create, list, test, delete notifications
- **Advanced Filtering**: By group, tag, name patterns, and monitor type
- **Bulk Notification Assignment**: Assign/remove notifications from multiple monitors
- **Query Parameter Filtering**: Use simple `?group=X&tag=Y` instead of JSON for all bulk operations
- **.env Configuration**: Simple environment variable setup
- **Zero Dependencies**: Just curl for all operations

## Quick Start

### 1. Installation

```bash
git clone https://github.com/keithah/uptime-kuma-rest-api.git
cd uptime-kuma-rest-api
pip install -r requirements.txt
```

### 2. Configuration

Copy the example environment file and configure it:

```bash
cp .env.example .env
```

Edit `.env`:
```bash
UPTIME_KUMA_URL=http://localhost:3001
UPTIME_KUMA_USERNAME=admin
UPTIME_KUMA_PASSWORD=your_password_here
```

### 3. Start the API

```bash
python uptime_kuma_rest_api.py
```

The API will be available at `http://127.0.0.1:5001`

## API Endpoints & Examples

### Health Check

Check if the API is connected and authenticated:

```bash
curl http://127.0.0.1:5001/health
```

### Monitor Management

#### List All Monitors
```bash
# List all monitors
curl http://127.0.0.1:5001/monitors

# List monitors in a specific group
curl "http://127.0.0.1:5001/monitors?group=Production"

# List monitors with a specific tag
curl "http://127.0.0.1:5001/monitors?tag=critical"

# List monitors matching name pattern (wildcards)
curl "http://127.0.0.1:5001/monitors?name_pattern=web-*"

# List monitors by type
curl "http://127.0.0.1:5001/monitors?type=http"

# Include groups in results
curl "http://127.0.0.1:5001/monitors?include_groups=true"
```

#### Create Single Monitor
```bash
curl -X POST http://127.0.0.1:5001/monitors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Website",
    "url": "https://example.com",
    "interval": 300,
    "maxretries": 3,
    "retryInterval": 60
  }'
```

#### Create Multiple Monitors
```bash
curl -X POST http://127.0.0.1:5001/monitors/bulk \
  -H "Content-Type: application/json" \
  -d '[
    {
      "name": "Website 1",
      "url": "https://example1.com"
    },
    {
      "name": "Website 2",
      "url": "https://example2.com"
    }
  ]'
```

#### Bulk Update Monitors

Update all monitors in a group (using query parameters):
```bash
curl -X PUT "http://127.0.0.1:5001/monitors/bulk-update?group=Media%20Playback" \
  -H "Content-Type: application/json" \
  -d '{
    "interval": 180,
    "retryInterval": 30,
    "maxretries": 3
  }'
```

Update monitors with specific tag (using query parameters):
```bash
curl -X PUT "http://127.0.0.1:5001/monitors/bulk-update?tag=production" \
  -H "Content-Type: application/json" \
  -d '{
    "timeout": 45
  }'
```

Update monitors matching name pattern (using query parameters):
```bash
curl -X PUT "http://127.0.0.1:5001/monitors/bulk-update?name_pattern=api-*" \
  -H "Content-Type: application/json" \
  -d '{
    "interval": 60,
    "maxretries": 5
  }'
```

You can also use the traditional JSON body format:
```bash
curl -X PUT http://127.0.0.1:5001/monitors/bulk-update \
  -H "Content-Type: application/json" \
  -d '{
    "filters": {
      "group": "Media Playback"
    },
    "updates": {
      "interval": 180,
      "retryInterval": 30,
      "maxretries": 3
    }
  }'
```

#### Monitor Control Operations

```bash
# Pause a monitor
curl -X POST http://127.0.0.1:5001/monitors/123/pause

# Resume a monitor
curl -X POST http://127.0.0.1:5001/monitors/123/resume

# Delete a monitor
curl -X DELETE http://127.0.0.1:5001/monitors/123
```

#### Bulk Monitor Control

Pause all monitors in a group (using query parameters):
```bash
curl -X POST "http://127.0.0.1:5001/monitors/bulk-control?group=Maintenance&action=pause" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Resume monitors with specific tag (using query parameters):
```bash
curl -X POST "http://127.0.0.1:5001/monitors/bulk-control?tag=staging&action=resume" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Delete monitors matching name pattern (using query parameters):
```bash
curl -X POST "http://127.0.0.1:5001/monitors/bulk-control?name_pattern=temp-*&action=delete" \
  -H "Content-Type: application/json" \
  -d '{}'
```

You can also use the traditional JSON body format:
```bash
curl -X POST http://127.0.0.1:5001/monitors/bulk-control \
  -H "Content-Type: application/json" \
  -d '{
    "filters": {
      "group": "Maintenance"
    },
    "action": "pause"
  }'
```

### Notification Management

#### List All Notifications
```bash
curl http://127.0.0.1:5001/notifications
```

#### Create Notification
```bash
# Slack notification example
curl -X POST http://127.0.0.1:5001/notifications \
  -H "Content-Type: application/json" \
  -d '{
    "type": "slack",
    "name": "Production Alerts",
    "slackWebhookURL": "https://hooks.slack.com/your-webhook-url",
    "slackChannel": "#alerts"
  }'

# Email notification example
curl -X POST http://127.0.0.1:5001/notifications \
  -H "Content-Type: application/json" \
  -d '{
    "type": "smtp",
    "name": "Email Alerts",
    "smtpHost": "smtp.gmail.com",
    "smtpPort": 587,
    "smtpSecure": "tls",
    "smtpUsername": "your-email@gmail.com",
    "smtpPassword": "your-password",
    "emailFrom": "alerts@yourcompany.com",
    "emailTo": "admin@yourcompany.com"
  }'
```

#### Test Notification
```bash
curl -X POST http://127.0.0.1:5001/notifications/1/test
```

#### Delete Notification
```bash
curl -X DELETE http://127.0.0.1:5001/notifications/1
```

#### Notification Management

First, get your notification IDs:
```bash
# Get notification IDs and names
curl "http://127.0.0.1:5001/notifications?simple=true"
```

#### Set Notifications (Recommended - Simple!)

Replace all notifications for monitors in one command:
```bash
# Set ms-alerts (ID 2) for all Tailscale monitors
curl -X PUT "http://127.0.0.1:5001/monitors/set-notifications?group=Tailscale&notification_ids=2" \
  -H "Content-Type: application/json" \
  -d '{}'

# Set hadm-plex (ID 1) for Media Playback group
curl -X PUT "http://127.0.0.1:5001/monitors/set-notifications?group=Media%20Playback&notification_ids=1" \
  -H "Content-Type: application/json" \
  -d '{}'

# Set multiple notifications for critical monitors
curl -X PUT "http://127.0.0.1:5001/monitors/set-notifications?tag=critical&notification_ids=1,2" \
  -H "Content-Type: application/json" \
  -d '{}'

# Clear all notifications from monitors
curl -X PUT "http://127.0.0.1:5001/monitors/set-notifications?group=Test&notification_ids=" \
  -H "Content-Type: application/json" \
  -d '{}'
```

#### Add/Remove Notifications (Advanced)

Add notifications to monitors:
```bash
curl -X PUT "http://127.0.0.1:5001/monitors/bulk-notifications?group=Production&notification_ids=1,2&action=add" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Remove specific notifications:
```bash
curl -X PUT "http://127.0.0.1:5001/monitors/bulk-notifications?tag=maintenance&notification_ids=1&action=remove" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Settings

#### Get Current Settings
```bash
curl http://127.0.0.1:5001/settings
```

## Filtering Options

All bulk operations support these filter combinations:

- `group`: Filter by monitor group name
- `tag`: Filter by tag name
- `name_pattern`: Filter by name using wildcards (`*`, `?`)
- `type`: Filter by monitor type (`http`, `tcp`, `dns`, etc.)
- `include_groups`: Include group monitors in results (default: false)

### Filter Examples

```bash
# Multiple filters using query parameters (AND logic)
curl -X PUT "http://127.0.0.1:5001/monitors/bulk-update?group=Production&tag=critical&type=http" \
  -H "Content-Type: application/json" \
  -d '{"interval": 60}'

# Same thing using JSON body format
curl -X PUT http://127.0.0.1:5001/monitors/bulk-update \
  -H "Content-Type: application/json" \
  -d '{
    "filters": {
      "group": "Production",
      "tag": "critical",
      "type": "http"
    },
    "updates": {
      "interval": 60
    }
  }'
```

**Note:** Query parameters take precedence over JSON body filters when both are provided.

## Configuration Options

Environment variables in `.env`:

```bash
# Required
UPTIME_KUMA_URL=http://localhost:3001
UPTIME_KUMA_USERNAME=admin
UPTIME_KUMA_PASSWORD=your_password_here

# Optional API server settings
API_HOST=127.0.0.1
API_PORT=5001
API_DEBUG=false
```

## Common Use Cases

### 1. Update All Production Monitors (Simple Query Params)
```bash
curl -X PUT "http://127.0.0.1:5001/monitors/bulk-update?tag=production" \
  -H "Content-Type: application/json" \
  -d '{"interval": 300, "maxretries": 3}'
```

### 2. Set Notifications for Critical Services (Simple!)
```bash
# First get notification IDs
curl "http://127.0.0.1:5001/notifications?simple=true"
# Then set the notifications
curl -X PUT "http://127.0.0.1:5001/monitors/set-notifications?tag=critical&notification_ids=1" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 3. Pause All Staging Monitors (Simple Query Params)
```bash
curl -X POST "http://127.0.0.1:5001/monitors/bulk-control?group=Staging&action=pause" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 4. Update All API Monitors (Simple Query Params)
```bash
curl -X PUT "http://127.0.0.1:5001/monitors/bulk-update?name_pattern=*api*" \
  -H "Content-Type: application/json" \
  -d '{"timeout": 30, "interval": 120}'
```

### 5. Complex Multi-Filter Example
```bash
# Update all HTTP monitors in Production group with critical tag
curl -X PUT "http://127.0.0.1:5001/monitors/bulk-update?group=Production&tag=critical&type=http" \
  -H "Content-Type: application/json" \
  -d '{"interval": 60, "timeout": 45}'
```

## Error Handling

All endpoints return JSON responses with consistent error format:

```json
{
  "success": false,
  "error": "Error description"
}
```

Successful bulk operations return detailed results:

```json
{
  "results": [...],
  "total": 10,
  "successful": 9,
  "failed": 1
}
```

## Requirements

- Python 3.7+
- Uptime Kuma server with authentication enabled
- Network access to your Uptime Kuma instance

## Limitations

- Uses Uptime Kuma's internal Socket.io API (not officially supported)
- API may break with future Uptime Kuma updates
- Rate limited by Socket.io timeouts

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