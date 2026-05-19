import os
import platform
import time
import json
import psutil
import subprocess
from flask import Flask, render_template, jsonify, request
from gevent import pywsgi
from geventwebsocket.handler import WebSocketHandler

app = Flask(__name__)

# Config
PORT = int(os.environ.get('PORT', 5000))
HOST = os.environ.get('HOST', '0.0.0.0')

def get_system_info():
    """Get basic system info"""
    return {
        'hostname': platform.node(),
        'os': f"{platform.system()} {platform.release()}",
        'arch': platform.machine(),
        'python_version': platform.python_version(),
        'uptime': get_uptime()
    }

def get_uptime():
    """Get system uptime"""
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.readline().split()[0])
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            return f"{days}d {hours}h {minutes}m"
    except:
        return "Unknown"

def get_cpu_metrics():
    """Get CPU metrics"""
    cpu_percent = psutil.cpu_percent(interval=0.1, percpu=True)
    cpu_freq = psutil.cpu_freq()
    load_avg = os.getloadavg() if hasattr(os, 'getloadavg') else [0, 0, 0]
    
    return {
        'usage_total': round(sum(cpu_percent) / len(cpu_percent), 1),
        'usage_per_core': [round(p, 1) for p in cpu_percent],
        'core_count': psutil.cpu_count(),
        'frequency_current': round(cpu_freq.current, 0) if cpu_freq else 0,
        'frequency_max': round(cpu_freq.max, 0) if cpu_freq else 0,
        'load_avg': [round(l, 2) for l in load_avg]
    }

def get_memory_metrics():
    """Get memory metrics"""
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    
    return {
        'ram_total': round(mem.total / (1024**3), 2),
        'ram_used': round(mem.used / (1024**3), 2),
        'ram_free': round(mem.free / (1024**3), 2),
        'ram_percent': mem.percent,
        'swap_total': round(swap.total / (1024**3), 2),
        'swap_used': round(swap.used / (1024**3), 2),
        'swap_percent': swap.percent
    }

def get_disk_metrics():
    """Get disk metrics"""
    partitions = psutil.disk_partitions()
    disks = []
    
    for partition in partitions:
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            disks.append({
                'device': partition.device,
                'mountpoint': partition.mountpoint,
                'fstype': partition.fstype,
                'total': round(usage.total / (1024**3), 1),
                'used': round(usage.used / (1024**3), 1),
                'free': round(usage.free / (1024**3), 1),
                'percent': usage.percent
            })
        except:
            pass
    
    return disks

def get_network_metrics():
    """Get network metrics"""
    net_io = psutil.net_io_counters()
    interfaces = {}
    
    for iface, stats in psutil.net_io_counters(pernic=True).items():
        interfaces[iface] = {
            'bytes_sent': stats.bytes_sent,
            'bytes_recv': stats.bytes_recv,
            'packets_sent': stats.packets_sent,
            'packets_recv': stats.packets_recv,
            'errin': stats.errin,
            'errout': stats.errout,
            'dropin': stats.dropin,
            'dropout': stats.dropout
        }
    
    return {
        'total': {
            'bytes_sent': net_io.bytes_sent,
            'bytes_recv': net_io.bytes_recv,
            'packets_sent': net_io.packets_sent,
            'packets_recv': net_io.packets_recv
        },
        'interfaces': interfaces
    }

def get_processes():
    """Get process list"""
    processes = []
    for p in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent', 'status']):
        try:
            info = p.info
            processes.append({
                'pid': info['pid'],
                'name': info['name'][:50],
                'user': info['username'][:20] if info['username'] else 'root',
                'cpu': round(info['cpu_percent'] or 0, 1),
                'memory': round(info['memory_percent'] or 0, 1),
                'status': info['status']
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    # Sort by CPU usage
    processes.sort(key=lambda x: x['cpu'], reverse=True)
    return processes[:50]  # Top 50

def get_temperature():
    """Get temperature if available"""
    temps = {}
    try:
        temp = psutil.sensors_temperatures()
        for name, entries in temp.items():
            if entries:
                temps[name] = round(entries[0].current, 1)
    except:
        pass
    return temps

def get_battery():
    """Get battery info if available"""
    try:
        battery = psutil.sensors_battery()
        if battery:
            return {
                'percent': battery.percent,
                'charging': battery.is_charging,
                'time_left': battery.secsleft if battery.secsleft != psutil.POWER_TIME_UNLIMITED else None
            }
    except:
        pass
    return None

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')

@app.route('/api/system')
def api_system():
    """System info endpoint"""
    return jsonify(get_system_info())

@app.route('/api/cpu')
def api_cpu():
    """CPU metrics endpoint"""
    return jsonify(get_cpu_metrics())

@app.route('/api/memory')
def api_memory():
    """Memory metrics endpoint"""
    return jsonify(get_memory_metrics())

@app.route('/api/disk')
def api_disk():
    """Disk metrics endpoint"""
    return jsonify(get_disk_metrics())

@app.route('/api/network')
def api_network():
    """Network metrics endpoint"""
    return jsonify(get_network_metrics())

@app.route('/api/processes')
def api_processes():
    """Process list endpoint"""
    return jsonify(get_processes())

@app.route('/api/temp')
def api_temp():
    """Temperature endpoint"""
    return jsonify(get_temperature())

@app.route('/api/battery')
def api_battery():
    """Battery endpoint"""
    return jsonify(get_battery())

@app.route('/api/all')
def api_all():
    """All metrics combined"""
    return jsonify({
        'system': get_system_info(),
        'cpu': get_cpu_metrics(),
        'memory': get_memory_metrics(),
        'disk': get_disk_metrics(),
        'network': get_network_metrics(),
        'processes': get_processes(),
        'temperature': get_temperature(),
        'battery': get_battery(),
        'timestamp': time.time()
    })

@app.route('/api/command', methods=['POST'])
def api_command():
    """Execute command in terminal"""
    data = request.get_json()
    cmd = data.get('command', '')
    
    try:
        # Limit execution time and output
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        output = result.stdout if result.stdout else result.stderr
        return jsonify({'output': output[:5000]})  # Limit output size
    except subprocess.TimeoutExpired:
        return jsonify({'output': 'Command timed out'})
    except Exception as e:
        return jsonify({'output': str(e)})

if __name__ == '__main__':
    print(f"="*50)
    print(f"  Home Server Dashboard")
    print(f"  Access: http://{HOST}:{PORT}")
    print(f"="*50)
    
    server = pywsgi.WSGIServer((HOST, PORT), app, handler_class=WebSocketHandler)
    server.serve_forever()
