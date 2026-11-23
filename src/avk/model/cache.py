"""Where compiled kernels live: `AVK_CACHE_DIR`, else the user cache directory.

Generated kernel modules go to `<root>/kernels/<code>-<identity16>/kernel.py`, Numba's own
cache to `NUMBA_CACHE_DIR`, which AVK points at `<root>/numba` when it is unset (on import
of `avk`, before Numba reads its configuration). Standard library only, so the package
import can call it before Numba loads.
"""

import os
import sys
from pathlib import Path


def cache_root() -> Path:
    """`AVK_CACHE_DIR`, else the platform's user cache directory for Actuary Valuation Kit."""
    configured = os.environ.get("AVK_CACHE_DIR")
    if configured:
        return Path(configured).expanduser()
    home = Path.home()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or home / "AppData/Local") / "avk/Cache"
    if sys.platform == "darwin":
        return home / "Library/Caches/avk"
    return Path(os.environ.get("XDG_CACHE_HOME") or home / ".cache") / "avk"


def numba_cache_dir() -> Path:
    """Numba's cache: `NUMBA_CACHE_DIR` when set, else beside the kernel modules."""
    configured = os.environ.get("NUMBA_CACHE_DIR")
    return Path(configured) if configured else cache_root() / "numba"


def default_numba_cache_dir() -> None:
    """Point `NUMBA_CACHE_DIR` at the AVK cache unless the user chose another place."""
    os.environ.setdefault("NUMBA_CACHE_DIR", str(cache_root() / "numba"))
