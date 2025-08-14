#!/usr/bin/env python3
"""
Bulk update monitors in a specific group.
This example shows how to update all monitors in a group with new settings.
"""
import socketio
import time
import os
import sys

# Configuration from environment
UPTIME_KUMA_URL = os.getenv("UPTIME_KUMA_URL", "http://localhost:3001")
USERNAME = os.getenv("UPTIME_KUMA_USERNAME", "admin")
PASSWORD = os.getenv("UPTIME_KUMA_PASSWORD", "admin")

def bulk_update_monitors_by_group(group_name, settings):
    """
    Update all monitors in a specific group with new settings.
    
    Args:
        group_name: Name of the monitor group
        settings: Dictionary of settings to update (e.g., {'interval': 180, 'maxretries': 3})
    """
    sio = socketio.Client()
    monitors_updated = 0
    
    @sio.event
    def connect():
        print(f"Connected to {UPTIME_KUMA_URL}")
    
    @sio.event
    def disconnect():
        print("Disconnected")
    
    @sio.on('monitorList')
    def on_monitor_list(data):
        nonlocal monitors_updated
        
        # Find the group ID
        group_id = None
        for monitor_id, monitor in data.items():
            if monitor.get('name') == group_name and monitor.get('type') == 'group':
                group_id = monitor['id']
                print(f"Found group '{group_name}' with ID: {group_id}")
                break
        
        if not group_id:
            print(f"Group '{group_name}' not found")
            sio.disconnect()
            return
        
        # Find and update monitors in the group
        monitors_to_update = []
        for monitor_id, monitor in data.items():
            if monitor.get('parent') == group_id:
                monitors_to_update.append(monitor)
        
        print(f"Found {len(monitors_to_update)} monitors in group '{group_name}'")
        
        # Update each monitor
        for monitor in monitors_to_update:
            # Apply new settings
            for key, value in settings.items():
                monitor[key] = value
            
            def edit_callback(response):
                nonlocal monitors_updated
                if response and response.get('ok'):
                    monitors_updated += 1
                    print(f"✓ Updated {monitor['name']}")
                else:
                    print(f"✗ Failed to update {monitor['name']}: {response}")
            
            sio.emit('editMonitor', monitor, callback=edit_callback)
            time.sleep(0.5)  # Small delay between updates
    
    # Connect and authenticate
    try:
        sio.connect(UPTIME_KUMA_URL)
        time.sleep(1)
        
        # Authenticate
        auth_success = False
        def auth_callback(response):
            nonlocal auth_success
            if response and response.get('ok'):
                print("Authentication successful")
                auth_success = True
            else:
                print(f"Authentication failed: {response}")
        
        sio.emit('login', {
            'username': USERNAME,
            'password': PASSWORD,
            'token': ''
        }, callback=auth_callback)
        
        # Wait for authentication
        time.sleep(2)
        
        if not auth_success:
            print("Failed to authenticate")
            return
        
        # Wait for monitor list and updates
        time.sleep(5 + len(monitors_to_update) * 0.5)
        
        print(f"\nCompleted {monitors_updated} updates")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        sio.disconnect()

if __name__ == "__main__":
    # Example usage
    if len(sys.argv) < 2:
        print("Usage: python bulk_update_by_group.py <group_name>")
        print("Example: python bulk_update_by_group.py 'Media Playback'")
        sys.exit(1)
    
    group_name = sys.argv[1]
    
    # Settings to apply to all monitors in the group
    settings = {
        'interval': 180,        # 3 minutes
        'retryInterval': 30,    # 30 seconds
        'maxretries': 3         # 3 retries
    }
    
    print(f"Updating all monitors in group '{group_name}' with:")
    for key, value in settings.items():
        print(f"  {key}: {value}")
    print()
    
    bulk_update_monitors_by_group(group_name, settings)