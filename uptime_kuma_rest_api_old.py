#!/usr/bin/env python3
"""
REST API wrapper for Uptime Kuma's Socket.io API
Provides HTTP endpoints for creating monitors programmatically
"""

from flask import Flask, request, jsonify
import socketio
import time
import os
from typing import Dict, Any

app = Flask(__name__)

# Uptime Kuma connection details - configure via environment variables
UPTIME_KUMA_URL = os.getenv("UPTIME_KUMA_URL", "http://localhost:3001")
USERNAME = os.getenv("UPTIME_KUMA_USERNAME", "admin")
PASSWORD = os.getenv("UPTIME_KUMA_PASSWORD", "admin")

class UptimeKumaClient:
    def __init__(self):
        self.sio = None
        self.authenticated = False
        
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
        
        try:
            self.sio.connect(UPTIME_KUMA_URL)
            time.sleep(1)
            return True
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            return False
    
    def authenticate(self):
        """Authenticate with Uptime Kuma using callback method"""
        if not self.sio or not self.sio.connected:
            return False
            
        def login_callback(response):
            self.authenticated = response.get('ok', False)
            if self.authenticated:
                print("✓ Authentication successful")
            else:
                print(f"✗ Authentication failed: {response}")
            
        self.sio.emit('login', {
            'username': USERNAME,
            'password': PASSWORD,
            'token': ''
        }, callback=login_callback)
        
        # Wait for authentication
        timeout = 10
        while not self.authenticated and timeout > 0:
            time.sleep(0.1)
            timeout -= 0.1
            
        return self.authenticated
    
    def create_monitor(self, monitor_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new monitor using callback method"""
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
    
    def disconnect(self):
        """Disconnect from Uptime Kuma"""
        if self.sio:
            self.sio.disconnect()

# Global client instance
kuma_client = UptimeKumaClient()

def connect_to_kuma():
    """Connect to Uptime Kuma on startup"""
    if kuma_client.connect():
        kuma_client.authenticate()

# Connect on startup
connect_to_kuma()

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
    """Manually connect to Uptime Kuma"""
    success = kuma_client.connect()
    if success:
        auth_success = kuma_client.authenticate()
        return jsonify({
            'connected': success,
            'authenticated': auth_success
        })
    else:
        return jsonify({'connected': False, 'authenticated': False}), 500

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
        
        results.append({
            'index': i,
            'name': monitor_data.get('name', 'Unknown'),
            'success': result.get('ok', False),
            'monitorID': result.get('monitorID') if result.get('ok') else None,
            'error': result.get('msg') if not result.get('ok') else None
        })
        
        # Small delay between creations
        time.sleep(0.5)
    
    success_count = sum(1 for r in results if r['success'])
    
    return jsonify({
        'total': len(monitors_data),
        'successful': success_count,
        'failed': len(monitors_data) - success_count,
        'results': results
    })

if __name__ == '__main__':
    print(f"Starting Uptime Kuma REST API wrapper...")
    print(f"Will connect to: {UPTIME_KUMA_URL}")
    print(f"Username: {USERNAME}")
    
    app.run(host='127.0.0.1', port=5001, debug=True)