"""Bounded, privacy-preserving observations from this API process."""

import math
import os
import resource
import statistics
import threading
import time
from collections import deque
from pathlib import Path

from api.config import settings
from api.db import utcnow

_samples = deque(maxlen=2000)
_graph_samples = deque(maxlen=2000)
_lock = threading.Lock()
_started = time.monotonic()
_requests = _errors = 0
_storage = None
_storage_at = 0
_storage_lock = threading.Lock()


def record_request(status, milliseconds):
    global _requests, _errors
    with _lock:
        _samples.append((utcnow().isoformat(), milliseconds, status))
        _requests += 1
        _errors += int(status >= 500)


def record_graph_read(milliseconds, success):
    with _lock:
        _graph_samples.append((milliseconds, success))


def request_metrics():
    with _lock:
        samples = list(_samples)
        requests, errors = _requests, _errors
        graph = list(_graph_samples)
    ordered = sorted(s[1] for s in samples)
    graph_times = sorted(s[0] for s in graph)
    return {
        "scope": "Current API process; last 2,000 response-header timings; resets on restart",
        "uptime_seconds": round(time.monotonic() - _started),
        "requests_since_start": requests,
        "application_errors_since_start": errors,
        "window_samples": len(samples),
        "window_started_at": samples[0][0] if samples else None,
        "p50_ms": round(statistics.median(ordered), 2) if ordered else None,
        "p95_ms": round(ordered[math.ceil(len(ordered) * 0.95) - 1], 2) if ordered else None,
        "api_peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2),
        "graph_reads": {
            "scope": "Current API process, last 2,000 graph reads; query text and parameters are never retained",
            "samples": len(graph),
            "errors": sum(not row[1] for row in graph),
            "p50_ms": round(statistics.median(graph_times), 2) if graph_times else None,
            "p95_ms": round(graph_times[math.ceil(len(graph_times) * 0.95) - 1], 2)
            if graph_times
            else None,
        },
    }


def storage_metrics():
    global _storage, _storage_at
    with _storage_lock:
        if _storage is not None and time.monotonic() - _storage_at < 30:
            return _storage
        root = settings().data_dir.resolve()
        sizes = {}
        complete = True

        def scan_error(_):
            nonlocal complete
            complete = False

        entries = 0
        for name in ("snapshots", "uploads", "logs"):
            total = 0
            directory = root / name
            if directory.is_symlink():
                complete = False
                sizes[name] = None
                continue
            if not directory.exists():
                sizes[name] = 0
                continue
            for base, dirs, files in os.walk(directory, followlinks=False, onerror=scan_error):
                dirs[:] = [d for d in dirs if not Path(base, d).is_symlink()]
                entries += len(dirs) + len(files)
                if entries > 100000:
                    complete = False
                    break
                for file in files:
                    path = Path(base, file)
                    try:
                        if not path.is_symlink():
                            total += path.stat().st_size
                    except OSError:
                        complete = False
            sizes[name] = total
        _storage = {
            "bytes": sizes,
            "complete": complete,
            "measured_at": utcnow().isoformat(),
            "scope": "Source artifacts, uploaded inputs and archived logs; excludes database volumes and backups; cached for 30 seconds",
        }
        _storage_at = time.monotonic()
        return _storage
