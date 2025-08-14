#!/usr/bin/env python3
"""
List all monitors and their current configuration.
"""
import socketio
import time
import os

# Configuration from environment
UPTIME_KUMA_URL = os.getenv("UPTIME_KUMA_URL", "http://localhost:3001")
USERNAME = os.getenv("UPTIME_KUMA_USERNAME", "admin")
PASSWORD = os.getenv("UPTIME_KUMA_PASSWORD", "admin")

def list_monitors():
    """List all monitors with their configuration."""
    sio = socketio.Client()
    
    @sio.event
    def connect():
        print(f"Connected to {UPTIME_KUMA_URL}")
    
    @sio.event
    def disconnect():
        print("\nDisconnected")
    
    @sio.on('monitorList')
    def on_monitor_list(data):
        print(f"\nTotal monitors: {len(data)}")
        print("-" * 100)
        
        # Group monitors by type
        groups = {}
        standalone = []
        
        # First pass: identify groups
        for monitor_id, monitor in data.items():
            if monitor.get('type') == 'group':
                groups[monitor['id']] = {
                    'info': monitor,
                    'children': []
                }
        
        # Second pass: organize monitors
        for monitor_id, monitor in data.items():
            if monitor.get('type') != 'group':
                parent_id = monitor.get('parent')
                if parent_id and parent_id in groups:
                    groups[parent_id]['children'].append(monitor)
                else:
                    standalone.append(monitor)
        
        # Display grouped monitors
        for group_id, group_data in groups.items():
            group_info = group_data['info']
            print(f"\n📁 {group_info['name']} (Group ID: {group_info['id']})")
            print(f"   Children: {len(group_data['children'])}")
            
            for monitor in sorted(group_data['children'], key=lambda x: x['name']):
                print(f"   └─ {monitor['name']:<30} "
                      f"ID: {monitor['id']:<4} "
                      f"Type: {monitor['type']:<10} "
                      f"Interval: {monitor.get('interval', 'N/A')}s "
                      f"Retry: {monitor.get('retryInterval', 'N/A')}s "
                      f"Retries: {monitor.get('maxretries', 'N/A')}")
        
        # Display standalone monitors
        if standalone:
            print(f"\n📄 Standalone Monitors ({len(standalone)})")
            for monitor in sorted(standalone, key=lambda x: x['name']):
                print(f"   {monitor['name']:<30} "
                      f"ID: {monitor['id']:<4} "
                      f"Type: {monitor['type']:<10} "
                      f"Interval: {monitor.get('interval', 'N/A')}s")
        
        sio.disconnect()
    
    # Connect and authenticate
    try:
        sio.connect(UPTIME_KUMA_URL)
        time.sleep(1)
        
        # Authenticate
        def auth_callback(response):
            if response and response.get('ok'):
                print("Authentication successful")
            else:
                print(f"Authentication failed: {response}")
                sio.disconnect()
        
        sio.emit('login', {
            'username': USERNAME,
            'password': PASSWORD,
            'token': ''
        }, callback=auth_callback)
        
        # Wait for data
        time.sleep(3)
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_monitors()