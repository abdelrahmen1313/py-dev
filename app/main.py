"""
Linux Device Monitoring API
----------------------------
A small FastAPI application that exposes system information (CPU, memory,
disk, network, processes...) collected with psutil, protected by a simple
API key check.

Run it with:
    uvicorn main:app --host 0.0.0.0 --port 8000

See README.md for full setup and usage instructions.
"""

import os
import time
from datetime import datetime, timezone
from typing import Annotated

import psutil
from fastapi import FastAPI, Depends, HTTPException, Header, Security, status
from fastapi.security import APIKeyHeader
import uvicorn
from dotenv import load_dotenv
import socket
# import multiprocessing

# load custom env file
env_file = os.environ["WRKK_ENV_FILE"]

load_dotenv(dotenv_path=env_file, override=True)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# The API key is read from an environment variable so you never hardcode
# secrets in the source code. See README.md for how to set it.
API_KEY = os.getenv("MONITOR_API_KEY")

if not API_KEY:
    # Fail fast: it's better to refuse to start than to run unprotected.
    raise RuntimeError(
        "MONITOR_API_KEY environment variable is not set. "
        "Set it before starting the app, e.g.: export MONITOR_API_KEY='change-me'"
    )

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def verify_api_key(provided_key : str = Security(api_key_header)) -> str:
    """FastAPI dependency that validates the API key sent in the request header.

    Any route that depends on this function will automatically reject
    requests that don't present a valid `X-API-Key` header.
    """
    if provided_key is None or provided_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return provided_key

# get a free port from the os.
def get_free_port():
   s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
   s.bind(('', 0))
   port = s.getsockname()[1]
   s.close()
   return port


# ---------------------------------------------------------------------------
# Utils
# ---------------------------------------------------------------------------

def bytes_to_megabytes(bytes_value):
  return bytes_value / (1024 ** 2)


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Linux Monitor API",
    description="A minimal psutil-powered API for monitoring a Linux host.",
    version="1.0.0",
    docs_url=None, # Disable Swagger UI
    redoc_url=None # Disable ReDoc
)

# All routes below are grouped under /api and require a valid API key.
# We apply the dependency per-route (explicit and easy to understand),
# rather than globally, so it's obvious which endpoints are protected.

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health(_: str = Depends(verify_api_key)):
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# CPU
# ---------------------------------------------------------------------------

def convert_to_percent(load_tuple, log_cpu_count):
  percent_list = []
  for load in load_tuple:
    percent = (load / log_cpu_count) * 100
    percent_list.append(percent)

  return tuple(percent_list)

@app.get("/api/cpu")
def get_cpu(_: str = Depends(verify_api_key)):
    """CPU usage and basic info, similar to `top`/`mpstat`."""
    
    # simulating an mpstat cmd
    cpu_times = psutil.cpu_times()
    cpu_times_labels = ["user", "system", "idle", "nice", "iowait", 
                        "irq", "softirq", "steal", "guest", "guest_nice"]
    
    # Return CPU frequency as a namedtuple including current, min and max frequency expressed in Mhz.
    freq = psutil.cpu_freq()
    
    return {
        "mpstat" : dict(zip(cpu_times_labels, cpu_times)),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "usage_percent_per_core": psutil.cpu_percent(percpu=True, interval=1),
        "usage_percent_total": psutil.cpu_percent(interval=None),
        "frequency_mhz": {
            "current": freq.current if freq else None,
            "min": freq.min if freq else None,
            "max": freq.max if freq else None,
        },
        "load_average": convert_to_percent(psutil.getloadavg(), psutil.cpu_count(logical=True)) # (1min, 5min, 15min)
    }

# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------
@app.get("/api/memory")
def get_memory(_: str = Depends(verify_api_key)):
    """RAM and swap usage, similar to `free -h`."""
    virtual = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "virtual_memory": {
            "total": bytes_to_megabytes(virtual.total),
            "available": bytes_to_megabytes(virtual.available),
            "used": bytes_to_megabytes(virtual.used),
            "free": bytes_to_megabytes(virtual.free),
            "percent": virtual.percent,
        },
        "swap_memory": {
            "total": bytes_to_megabytes(swap.total),
            "used": bytes_to_megabytes(swap.used),
            "free": bytes_to_megabytes(swap.free),
            "percent": swap.percent,
        },
    }

# ---------------------------------------------------------------------------
# Disk
# ---------------------------------------------------------------------------
@app.get("/api/disk")
def get_disk(_: str = Depends(verify_api_key)):
    """Disk partitions/usage (similar to `df -h`) and IO counters."""
    partitions = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            partitions.append(
                {
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "total": bytes_to_megabytes(usage.total),
                    "used": bytes_to_megabytes(usage.used),
                    "free": bytes_to_megabytes(usage.free),
                    "percent": usage.percent,
                }
            )
        except PermissionError:
            # Some mountpoints (e.g. CD-ROM) may not be accessible; skip them.
            continue

    io_counters = psutil.disk_io_counters()
    return {
        "partitions": partitions,
        "io_counters": {
            "read_count": io_counters.read_count,
            "write_count": io_counters.write_count,
            "read_bytes": bytes_to_megabytes(io_counters.read_bytes),
            "write_bytes": bytes_to_megabytes(io_counters.write_bytes),
        }
        if io_counters
        else None,
    }

# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------
@app.get("/api/network")
def get_network(_: str = Depends(verify_api_key), list_interfaces : Annotated[str | None, Header()] = None):
    """Network IO counters and interface addresses (similar to `ifconfig`/`netstat`)."""
    io_counters = psutil.net_io_counters()
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    interfaces = {}
    if (list_interfaces):
      for name, addr_list in addrs.items():
        interfaces[name] = {
            "addresses": [
                {
                    "family": str(addr.family),
                    "address": addr.address,
                    "netmask": addr.netmask,
                    "broadcast": addr.broadcast,
                }
                for addr in addr_list
            ],
            "is_up": stats[name].isup if name in stats else None,
            "speed_mbps": stats[name].speed if name in stats else None,
        }

    return {
        "io_counters": {
            "bytes_sent": bytes_to_megabytes(io_counters.bytes_sent),
            "bytes_recv": bytes_to_megabytes(io_counters.bytes_recv),
            "packets_sent": io_counters.packets_sent,
            "packets_recv": io_counters.packets_recv,
            "errin": io_counters.errin,
            "errout": io_counters.errout,
            "mbps" : bytes_to_megabytes((io_counters.bytes_sent + io_counters.bytes_recv) * 8)
        },
        "interfaces": interfaces,
    }

# ---------------------------------------------------------------------------
# Processes
# ---------------------------------------------------------------------------
@app.get("/api/processes")
def get_processes(_: str = Depends(verify_api_key)):
    """List running processes with basic info, similar to `ps aux`."""
    processes = []
    for proc in psutil.process_iter(
        ["pid", "name", "username", "status", "cpu_percent", "memory_percent"]
    ):
        try:
            processes.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # A process may disappear between listing and reading its info.
            continue

    # Sort by CPU usage, descending, so the busiest processes appear first.
    processes.sort(key=lambda p: p.get("cpu_percent") or 0, reverse=True)
    return {"count": len(processes), "processes": processes}

# ---------------------------------------------------------------------------
# System / uptime
# ---------------------------------------------------------------------------
@app.get("/api/system")
def get_system(_: str = Depends(verify_api_key)):
    """General system info: boot time, uptime, users (similar to `uptime`/`who`)."""
    boot_timestamp = psutil.boot_time()
    boot_time = datetime.fromtimestamp(boot_timestamp, tz=timezone.utc)
    uptime_seconds = time.time() - boot_timestamp

    users = [
        {
            "name": u.name,
            "terminal": u.terminal,
            "host": u.host,
            "started": datetime.fromtimestamp(u.started, tz=timezone.utc).isoformat(),
        }
        for u in psutil.users()
    ]

    return {
        "boot_time_utc": boot_time.isoformat(),
        "uptime_seconds": uptime_seconds,
        "users": users,
    }


if __name__ == "__main__":
  # multiprocessing.freeze_support() # Required for Windows - ignore for now
  uvicorn.run(app, host="0.0.0.0", port=get_free_port())
