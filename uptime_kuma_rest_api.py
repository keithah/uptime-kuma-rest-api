#!/usr/bin/env python3
"""
REST API wrapper for Uptime Kuma's Socket.io API
Provides comprehensive HTTP endpoints for monitor and notification management
"""

from flask import Flask, request, jsonify
import socketio
import time
import os
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
import fnmatch

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Configuration from environment variables
UPTIME_KUMA_URL = os.getenv("UPTIME_KUMA_URL", "http://localhost:3001")
USERNAME = os.getenv("UPTIME_KUMA_USERNAME", "admin")
PASSWORD = os.getenv("UPTIME_KUMA_PASSWORD", "admin")
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "5001"))
API_DEBUG = os.getenv("API_DEBUG", "false").lower() == "true"

class UptimeKumaClient:
    def __init__(self):
        self.sio = None
        self.authenticated = False
        self.monitors_cache = {}
        self.notifications_cache = {}
        self.last_update = 0
        
    def connect(self):
        """Connect to Uptime Kuma"""
        self.sio = socketio.Client()
        
        @self.sio.event
        def connect():
            print(f"✓ Connected to {UPTIME_KUMA_URL}")
        
        @self.sio.event
        def disconnect():
            print("Disconnected from Uptime Kuma")
            self.authenticated = False
        
        @self.sio.on('monitorList')
        def on_monitor_list(data):
            self.monitors_cache = data
            self.last_update = time.time()
        
        @self.sio.on('notificationList')
        def on_notification_list(data):
            self.notifications_cache = data
        
        try:
            self.sio.connect(UPTIME_KUMA_URL)
            time.sleep(1)
            return True
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            return False
    
    def authenticate(self):
        """Authenticate with Uptime Kuma"""
        if not self.sio or not self.sio.connected:
            return False
        
        result = {'ok': False}
        
        def auth_callback(response):
            nonlocal result
            result = response or {'ok': False}
        
        self.sio.emit('login', {
            'username': USERNAME,
            'password': PASSWORD,
            'token': ''
        }, callback=auth_callback)
        
        # Wait for callback response
        timeout = 50  # 5 seconds
        while not result.get('ok') and timeout > 0:
            time.sleep(0.1)
            timeout -= 1
        
        self.authenticated = result.get('ok', False)
        if self.authenticated:
            print("✓ Authentication successful")
            time.sleep(1)  # Wait for monitor list
        else:
            print(f"✗ Authentication failed: {result}")
        
        return self.authenticated
    
    def create_monitor(self, monitor_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new monitor"""
        if not self.authenticated:
            return {'ok': False, 'error': 'Not authenticated'}
        
        result = {'ok': False, 'error': 'No response received'}
        
        def add_callback(response):
            nonlocal result
            result = response
        
        self.sio.emit('add', monitor_data, callback=add_callback)
        
        # Wait for callback response
        timeout = 100  # 10 seconds
        while result.get('ok') is False and 'No response received' in str(result.get('error', '')) and timeout > 0:
            time.sleep(0.1)
            timeout -= 1
        
        return result
    
    def update_monitor(self, monitor_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing monitor"""
        if not self.authenticated:
            return {'ok': False, 'error': 'Not authenticated'}
        
        result = {'ok': False, 'error': 'No response received'}
        
        def edit_callback(response):
            nonlocal result
            result = response
        
        self.sio.emit('editMonitor', monitor_data, callback=edit_callback)
        
        # Wait for callback response
        timeout = 100
        while result.get('ok') is False and 'No response received' in str(result.get('error', '')) and timeout > 0:
            time.sleep(0.1)
            timeout -= 1
        
        return result
    
    def get_monitors(self) -> Dict[str, Any]:
        """Get all monitors"""
        # Refresh cache if it's old
        if time.time() - self.last_update > 30:
            time.sleep(1)  # Wait for fresh data
        return self.monitors_cache
    
    def filter_monitors(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Filter monitors based on criteria"""
        monitors = self.get_monitors()
        results = []
        
        for monitor_id, monitor in monitors.items():
            # Skip groups unless explicitly requested
            if monitor.get('type') == 'group' and not filters.get('include_groups', False):
                continue
                
            match = True
            
            # Filter by group name
            if 'group' in filters:
                group_name = filters['group']
                parent_id = monitor.get('parent')
                if parent_id:
                    parent_monitor = monitors.get(str(parent_id), {})
                    if parent_monitor.get('name') != group_name:
                        match = False
                else:
                    match = False
            
            # Filter by tag
            if 'tag' in filters and match:
                tag_filter = filters['tag']
                monitor_tags = [tag.get('name', '') for tag in monitor.get('tags', [])]
                if tag_filter not in monitor_tags:
                    match = False
            
            # Filter by name pattern (wildcard)
            if 'name_pattern' in filters and match:
                pattern = filters['name_pattern']
                if not fnmatch.fnmatch(monitor.get('name', ''), pattern):
                    match = False
            
            # Filter by type
            if 'type' in filters and match:
                if monitor.get('type') != filters['type']:
                    match = False
            
            if match:
                results.append(monitor)
        
        return results

# Global client instance
kuma_client = UptimeKumaClient()

def extract_filters():
    """Extract filters from both query parameters and JSON body, with query params taking precedence"""
    filters = {}
    
    # Start with JSON body filters if present (only for requests with JSON)
    if request.is_json and request.json and 'filters' in request.json:
        filters.update(request.json['filters'])
    
    # Override with query parameters (query params take precedence)
    if request.args.get('group'):
        filters['group'] = request.args.get('group')
    if request.args.get('tag'):
        filters['tag'] = request.args.get('tag')
    if request.args.get('name_pattern'):
        filters['name_pattern'] = request.args.get('name_pattern')
    if request.args.get('type'):
        filters['type'] = request.args.get('type')
    if request.args.get('include_groups') == 'true':
        filters['include_groups'] = True
    
    return filters

def connect_to_kuma():
    """Connect to Uptime Kuma on startup"""
    if kuma_client.connect():
        kuma_client.authenticate()

# Connect on startup
connect_to_kuma()

# REST API Endpoints

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'connected': kuma_client.sio.connected if kuma_client.sio else False,
        'authenticated': kuma_client.authenticated
    })

@app.route('/connect', methods=['POST'])
def connect():
    """Manually reconnect to Uptime Kuma"""
    success = kuma_client.connect()
    if success:
        auth_success = kuma_client.authenticate()
        return jsonify({
            'connected': success,
            'authenticated': auth_success
        })
    else:
        return jsonify({'connected': False, 'authenticated': False}), 500

# Monitor Management Endpoints

@app.route('/monitors', methods=['GET'])
def list_monitors():
    """List all monitors with optional filtering"""
    if not kuma_client.authenticated:
        return jsonify({'error': 'Not connected or authenticated'}), 401
    
    filters = extract_filters()
    
    if filters:
        monitors = kuma_client.filter_monitors(filters)
        return jsonify({'monitors': monitors, 'count': len(monitors)})
    else:
        monitors = kuma_client.get_monitors()
        return jsonify({'monitors': monitors, 'count': len(monitors)})

@app.route('/monitors', methods=['POST'])
def create_monitor():
    """Create a new monitor"""
    if not kuma_client.authenticated:
        return jsonify({'error': 'Not connected or authenticated'}), 401
    
    monitor_data = request.json
    if not monitor_data:
        return jsonify({'error': 'No monitor data provided'}), 400
    
    # Set defaults for HTTP monitors
    monitor_data.setdefault('type', 'http')
    monitor_data.setdefault('method', 'GET')
    monitor_data.setdefault('interval', 300)
    monitor_data.setdefault('maxretries', 3)
    monitor_data.setdefault('retryInterval', 60)
    monitor_data.setdefault('timeout', 30)
    monitor_data.setdefault('active', True)
    monitor_data.setdefault('accepted_statuscodes', ['200-299'])
    
    result = kuma_client.create_monitor(monitor_data)
    
    if result.get('ok'):
        return jsonify({
            'success': True,
            'monitorID': result.get('monitorID'),
            'message': 'Monitor created successfully'
        })
    else:
        return jsonify({
            'success': False,
            'error': result.get('msg', 'Unknown error')
        }), 400

@app.route('/monitors/bulk', methods=['POST'])
def create_bulk_monitors():
    """Create multiple monitors at once"""
    if not kuma_client.authenticated:
        return jsonify({'error': 'Not connected or authenticated'}), 401
    
    monitors_data = request.json
    if not monitors_data or not isinstance(monitors_data, list):
        return jsonify({'error': 'Expected array of monitor objects'}), 400
    
    results = []
    for i, monitor_data in enumerate(monitors_data):
        # Set defaults
        monitor_data.setdefault('type', 'http')
        monitor_data.setdefault('method', 'GET')
        monitor_data.setdefault('interval', 300)
        monitor_data.setdefault('maxretries', 3)
        monitor_data.setdefault('retryInterval', 60)
        monitor_data.setdefault('timeout', 30)
        monitor_data.setdefault('active', True)
        monitor_data.setdefault('accepted_statuscodes', ['200-299'])
        
        result = kuma_client.create_monitor(monitor_data)
        
        results.append({
            'index': i,
            'name': monitor_data.get('name', 'Unknown'),
            'success': result.get('ok', False),
            'monitorID': result.get('monitorID') if result.get('ok') else None,
            'error': result.get('msg') if not result.get('ok') else None
        })
        
        time.sleep(0.5)  # Small delay between creations
    
    return jsonify({
        'results': results,
        'total': len(results),
        'successful': sum(1 for r in results if r['success']),
        'failed': sum(1 for r in results if not r['success'])
    })

@app.route('/monitors/bulk-update', methods=['PUT'])
def bulk_update_monitors():
    """Bulk update monitors based on filters (supports both query params and JSON body)"""
    if not kuma_client.authenticated:
        return jsonify({'error': 'Not connected or authenticated'}), 401
    
    filters = extract_filters()
    
    # Get updates from JSON body
    updates = {}
    if request.json:
        updates = request.json.get('updates', request.json)
        # Remove 'filters' key if it exists in the updates
        updates.pop('filters', None)
    
    if not updates:
        return jsonify({'error': 'No updates provided'}), 400
    
    # Get monitors to update
    monitors_to_update = kuma_client.filter_monitors(filters)
    
    if not monitors_to_update:
        return jsonify({'message': 'No monitors found matching criteria', 'updated': 0})
    
    results = []
    for monitor in monitors_to_update:
        # Apply updates
        for key, value in updates.items():
            monitor[key] = value
        
        result = kuma_client.update_monitor(monitor)
        results.append({
            'id': monitor['id'],
            'name': monitor['name'],
            'success': result.get('ok', False),
            'error': result.get('msg') if not result.get('ok') else None
        })
        time.sleep(0.5)
    
    successful = sum(1 for r in results if r['success'])
    return jsonify({
        'results': results,
        'total': len(results),
        'successful': successful,
        'failed': len(results) - successful
    })

# Notification Management Endpoints

@app.route('/notifications', methods=['GET'])
def list_notifications():
    """List all notifications with simplified output option"""
    if not kuma_client.authenticated:
        return jsonify({'error': 'Not connected or authenticated'}), 401
    
    notifications = kuma_client.notifications_cache
    
    # Support simplified output for easy reference
    if request.args.get('simple') == 'true':
        simple_list = []
        # Check if notifications is a list or dict
        if isinstance(notifications, list):
            for notification in notifications:
                simple_list.append({
                    'id': notification.get('id'),
                    'name': notification.get('name', 'Unnamed'),
                    'type': notification.get('type', 'unknown'),
                    'active': notification.get('active', True)
                })
        else:
            for nid, notification in notifications.items():
                simple_list.append({
                    'id': int(nid),
                    'name': notification.get('name', 'Unnamed'),
                    'type': notification.get('type', 'unknown'),
                    'active': notification.get('active', True)
                })
        return jsonify({
            'notifications': simple_list,
            'count': len(simple_list),
            'usage_tip': 'Use the ID numbers in notification_ids for bulk operations'
        })
    
    return jsonify({'notifications': notifications, 'count': len(notifications)})

@app.route('/notifications', methods=['POST'])
def create_notification():
    """Create a new notification"""
    if not kuma_client.authenticated:
        return jsonify({'error': 'Not connected or authenticated'}), 401
    
    notification_data = request.json
    if not notification_data:
        return jsonify({'error': 'No notification data provided'}), 400
    
    result = {'ok': False, 'error': 'No response received'}
    
    def add_callback(response):
        nonlocal result
        result = response
    
    kuma_client.sio.emit('addNotification', {
        'notification': notification_data,
        'notificationID': None
    }, callback=add_callback)
    
    # Wait for callback response
    timeout = 100
    while result.get('ok') is False and 'No response received' in str(result.get('error', '')) and timeout > 0:
        time.sleep(0.1)
        timeout -= 1
    
    if result.get('ok'):
        return jsonify({
            'success': True,
            'id': result.get('id'),
            'message': 'Notification created successfully'
        })
    else:
        return jsonify({
            'success': False,
            'error': result.get('msg', 'Unknown error')
        }), 400

@app.route('/notifications/<int:notification_id>', methods=['DELETE'])
def delete_notification(notification_id):
    """Delete a notification"""
    if not kuma_client.authenticated:
        return jsonify({'error': 'Not connected or authenticated'}), 401
    
    result = {'ok': False, 'error': 'No response received'}
    
    def delete_callback(response):
        nonlocal result
        result = response
    
    kuma_client.sio.emit('deleteNotification', notification_id, callback=delete_callback)
    
    # Wait for callback response
    timeout = 100
    while result.get('ok') is False and 'No response received' in str(result.get('error', '')) and timeout > 0:
        time.sleep(0.1)
        timeout -= 1
    
    if result.get('ok'):
        return jsonify({
            'success': True,
            'message': 'Notification deleted successfully'
        })
    else:
        return jsonify({
            'success': False,
            'error': result.get('msg', 'Unknown error')
        }), 400

@app.route('/notifications/<int:notification_id>/test', methods=['POST'])
def test_notification(notification_id):
    """Test a notification"""
    if not kuma_client.authenticated:
        return jsonify({'error': 'Not connected or authenticated'}), 401
    
    # Get notification data - notifications_cache is a dict with string keys
    notifications = kuma_client.notifications_cache
    notification = notifications.get(str(notification_id))
    
    if not notification:
        return jsonify({'error': 'Notification not found'}), 404
    
    result = {'ok': False, 'error': 'No response received'}
    
    def test_callback(response):
        nonlocal result
        result = response
    
    # Use the notification object directly - the test endpoint expects the full notification
    kuma_client.sio.emit('testNotification', notification, callback=test_callback)
    
    # Wait for callback response
    timeout = 100
    while result.get('ok') is False and 'No response received' in str(result.get('error', '')) and timeout > 0:
        time.sleep(0.1)
        timeout -= 1
    
    if result.get('ok'):
        return jsonify({
            'success': True,
            'message': 'Notification test sent successfully'
        })
    else:
        return jsonify({
            'success': False,
            'error': result.get('msg', 'Unknown error')
        }), 400

# Bulk notification assignment to monitors
@app.route('/monitors/bulk-notifications', methods=['PUT'])
def bulk_assign_notifications():
    """Bulk assign/remove notifications to monitors based on filters (supports both query params and JSON body)"""
    if not kuma_client.authenticated:
        return jsonify({'error': 'Not connected or authenticated'}), 401
    
    filters = extract_filters()
    
    # Get notification_ids and action from JSON body or query params
    notification_ids = []
    action = request.args.get('action', 'add')  # Default to 'add'
    
    if request.json:
        notification_ids = request.json.get('notification_ids', [])
        action = request.json.get('action', action)
    
    # Also support comma-separated notification_ids in query params
    if request.args.get('notification_ids'):
        notification_ids = [int(x.strip()) for x in request.args.get('notification_ids').split(',')]
    
    if not notification_ids:
        return jsonify({'error': 'No notification IDs provided'}), 400
    
    # Get monitors to update
    monitors_to_update = kuma_client.filter_monitors(filters)
    
    if not monitors_to_update:
        return jsonify({'message': 'No monitors found matching criteria', 'updated': 0})
    
    results = []
    for monitor in monitors_to_update:
        # Update notification list - ensure it exists and is a dict
        if 'notificationIDList' not in monitor or not isinstance(monitor['notificationIDList'], dict):
            monitor['notificationIDList'] = {}
        
        if action == 'add':
            for nid in notification_ids:
                monitor['notificationIDList'][str(nid)] = True
        elif action == 'remove':
            for nid in notification_ids:
                if str(nid) in monitor['notificationIDList']:
                    del monitor['notificationIDList'][str(nid)]
        
        result = kuma_client.update_monitor(monitor)
        results.append({
            'id': monitor['id'],
            'name': monitor['name'],
            'success': result.get('ok', False),
            'error': result.get('msg') if not result.get('ok') else None
        })
        time.sleep(0.5)
    
    successful = sum(1 for r in results if r['success'])
    return jsonify({
        'results': results,
        'total': len(results),
        'successful': successful,
        'failed': len(results) - successful,
        'action': action
    })

# Streamlined notification replacement endpoint
@app.route('/monitors/set-notifications', methods=['PUT'])
def set_monitor_notifications():
    """Replace all notifications for monitors matching filters - much simpler than add/remove operations"""
    if not kuma_client.authenticated:
        return jsonify({'error': 'Not connected or authenticated'}), 401
    
    filters = extract_filters()
    
    # Get notification_ids from JSON body or query params
    notification_ids = []
    
    if request.json:
        notification_ids = request.json.get('notification_ids', [])
    
    # Also support comma-separated notification_ids in query params
    if request.args.get('notification_ids'):
        notification_ids = [int(x.strip()) for x in request.args.get('notification_ids').split(',')]
    
    # Allow empty list to clear all notifications
    if notification_ids is None:
        return jsonify({'error': 'notification_ids parameter is required (use empty array [] to clear all)'}), 400
    
    # Get monitors to update
    monitors_to_update = kuma_client.filter_monitors(filters)
    
    if not monitors_to_update:
        return jsonify({'message': 'No monitors found matching criteria', 'updated': 0})
    
    results = []
    for monitor in monitors_to_update:
        # Replace entire notification list
        new_notification_list = {}
        for nid in notification_ids:
            new_notification_list[str(nid)] = True
        
        monitor['notificationIDList'] = new_notification_list
        
        result = kuma_client.update_monitor(monitor)
        results.append({
            'id': monitor['id'],
            'name': monitor['name'],
            'success': result.get('ok', False),
            'error': result.get('msg') if not result.get('ok') else None,
            'notifications_set': notification_ids
        })
        time.sleep(0.5)
    
    successful = sum(1 for r in results if r['success'])
    return jsonify({
        'results': results,
        'total': len(results),
        'successful': successful,
        'failed': len(results) - successful,
        'notifications_set': notification_ids
    })

# Monitor Control Operations

@app.route('/monitors/<int:monitor_id>/pause', methods=['POST'])
def pause_monitor(monitor_id):
    """Pause a monitor"""
    if not kuma_client.authenticated:
        return jsonify({'error': 'Not connected or authenticated'}), 401
    
    result = {'ok': False, 'error': 'No response received'}
    
    def pause_callback(response):
        nonlocal result
        result = response
    
    kuma_client.sio.emit('pauseMonitor', monitor_id, callback=pause_callback)
    
    timeout = 100
    while result.get('ok') is False and 'No response received' in str(result.get('error', '')) and timeout > 0:
        time.sleep(0.1)
        timeout -= 1
    
    if result.get('ok'):
        return jsonify({'success': True, 'message': 'Monitor paused successfully'})
    else:
        return jsonify({'success': False, 'error': result.get('msg', 'Unknown error')}), 400

@app.route('/monitors/<int:monitor_id>/resume', methods=['POST'])
def resume_monitor(monitor_id):
    """Resume a monitor"""
    if not kuma_client.authenticated:
        return jsonify({'error': 'Not connected or authenticated'}), 401
    
    result = {'ok': False, 'error': 'No response received'}
    
    def resume_callback(response):
        nonlocal result
        result = response
    
    kuma_client.sio.emit('resumeMonitor', monitor_id, callback=resume_callback)
    
    timeout = 100
    while result.get('ok') is False and 'No response received' in str(result.get('error', '')) and timeout > 0:
        time.sleep(0.1)
        timeout -= 1
    
    if result.get('ok'):
        return jsonify({'success': True, 'message': 'Monitor resumed successfully'})
    else:
        return jsonify({'success': False, 'error': result.get('msg', 'Unknown error')}), 400

@app.route('/monitors/<int:monitor_id>', methods=['DELETE'])
def delete_monitor(monitor_id):
    """Delete a monitor"""
    if not kuma_client.authenticated:
        return jsonify({'error': 'Not connected or authenticated'}), 401
    
    result = {'ok': False, 'error': 'No response received'}
    
    def delete_callback(response):
        nonlocal result
        result = response
    
    kuma_client.sio.emit('deleteMonitor', monitor_id, callback=delete_callback)
    
    timeout = 100
    while result.get('ok') is False and 'No response received' in str(result.get('error', '')) and timeout > 0:
        time.sleep(0.1)
        timeout -= 1
    
    if result.get('ok'):
        return jsonify({'success': True, 'message': 'Monitor deleted successfully'})
    else:
        return jsonify({'success': False, 'error': result.get('msg', 'Unknown error')}), 400

# Bulk monitor control operations
@app.route('/monitors/bulk-control', methods=['POST'])
def bulk_control_monitors():
    """Bulk pause/resume/delete monitors based on filters (supports both query params and JSON body)"""
    if not kuma_client.authenticated:
        return jsonify({'error': 'Not connected or authenticated'}), 401
    
    filters = extract_filters()
    
    # Get action from JSON body or query params
    action = request.args.get('action')
    if request.json:
        action = request.json.get('action', action)
    
    if not action or action not in ['pause', 'resume', 'delete']:
        return jsonify({'error': 'Invalid action. Must be pause, resume, or delete'}), 400
    
    monitors_to_update = kuma_client.filter_monitors(filters)
    
    if not monitors_to_update:
        return jsonify({'message': 'No monitors found matching criteria', 'processed': 0})
    
    results = []
    for monitor in monitors_to_update:
        result = {'ok': False, 'error': 'No response received'}
        
        def action_callback(response):
            nonlocal result
            result = response
        
        if action == 'pause':
            kuma_client.sio.emit('pauseMonitor', monitor['id'], callback=action_callback)
        elif action == 'resume':
            kuma_client.sio.emit('resumeMonitor', monitor['id'], callback=action_callback)
        elif action == 'delete':
            kuma_client.sio.emit('deleteMonitor', monitor['id'], callback=action_callback)
        
        timeout = 100
        while result.get('ok') is False and 'No response received' in str(result.get('error', '')) and timeout > 0:
            time.sleep(0.1)
            timeout -= 1
        
        results.append({
            'id': monitor['id'],
            'name': monitor['name'],
            'success': result.get('ok', False),
            'error': result.get('msg') if not result.get('ok') else None
        })
        time.sleep(0.5)
    
    successful = sum(1 for r in results if r['success'])
    return jsonify({
        'results': results,
        'total': len(results),
        'successful': successful,
        'failed': len(results) - successful,
        'action': action
    })

# Settings Operations

@app.route('/settings', methods=['GET'])
def get_settings():
    """Get Uptime Kuma settings"""
    if not kuma_client.authenticated:
        return jsonify({'error': 'Not connected or authenticated'}), 401
    
    result = {'ok': False, 'error': 'No response received'}
    
    def settings_callback(response):
        nonlocal result
        result = response
    
    kuma_client.sio.emit('getSettings', callback=settings_callback)
    
    timeout = 100
    while result.get('ok') is False and 'No response received' in str(result.get('error', '')) and timeout > 0:
        time.sleep(0.1)
        timeout -= 1
    
    if result.get('ok'):
        return jsonify({'success': True, 'settings': result})
    else:
        return jsonify({'success': False, 'error': 'Failed to retrieve settings'}), 400

if __name__ == '__main__':
    print("\n=== Uptime Kuma REST API Wrapper ===")
    print(f"Will connect to: {UPTIME_KUMA_URL}")
    print(f"Username: {USERNAME}")
    print(f"API will be available at: http://{API_HOST}:{API_PORT}")
    print("=====================================\n")
    
    app.run(host=API_HOST, port=API_PORT, debug=API_DEBUG)