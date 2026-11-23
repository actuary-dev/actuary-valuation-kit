"""Complete public Term workload for the reference-laptop speed guard."""

import json
import os
import subprocess
import sys

SCRIPT = """
import json, resource, sys, time
from pathlib import Path
from avk.api import load_run_config, run
cfg = load_run_config(sys.argv[1]).model_copy(update={"output_path": sys.argv[2]})
started = time.perf_counter()
result = run(cfg)
wall = time.perf_counter() - started
status = Path("/proc/self/status")
try:
    lines = status.read_text().splitlines()
except FileNotFoundError:
    peak_rss_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    peak_rss_source = "ru_maxrss"
else:
    # VmHWM belongs to this address space; ru_maxrss may include the fork parent.
    hwm = next(line for line in lines if line.startswith("VmHWM:"))
    peak_rss_bytes = int(hwm.split()[1]) * 1024
    peak_rss_source = "/proc/self/status:VmHWM"
print(json.dumps({"wall": wall,
                  "peak_rss_bytes": peak_rss_bytes,
                  "peak_rss_source": peak_rss_source,
                  "timings": dict(result.timings), "kernels": dict(result.kernels)}))
"""


def timed(config, folder, *, cache=None, threads=16):
    env = {**os.environ, "NUMBA_NUM_THREADS": str(threads)}
    if cache is not None:
        env.pop("NUMBA_CACHE_DIR", None)
        env["AVK_CACHE_DIR"] = str(cache)
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, str(config), str(folder)],
        capture_output=True,
        text=True,
        env=env,
        timeout=900,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])
