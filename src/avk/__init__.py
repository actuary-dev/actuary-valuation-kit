"""Actuary Valuation Kit actuarial projection package; public operations live in avk.api."""

from avk.model.cache import default_numba_cache_dir

# Configure Numba's cache before any AVK module imports Numba.
default_numba_cache_dir()
