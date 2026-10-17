"""Run the optional real FalkorDBLite service on loopback for development."""

import signal
import threading
from pathlib import Path

from redislite.falkordb_client import FalkorDB

path = Path(".data/falkor.rdb").resolve()
path.parent.mkdir(parents=True, exist_ok=True)
db = FalkorDB(
    str(path),
    serverconfig={
        "bind": "127.0.0.1",
        "port": "56379",
        "appendonly": "yes",
        "dir": str(path.parent),
    },
)
print("FalkorDBLite ready on 127.0.0.1:56379", flush=True)
stopped = threading.Event()
for sig in (signal.SIGTERM, signal.SIGINT):
    signal.signal(sig, lambda *_: stopped.set())
stopped.wait()
db.connection.save()
