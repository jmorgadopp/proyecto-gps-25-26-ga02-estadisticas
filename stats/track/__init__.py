"""Compatibility shim: expose `stats.track` while implementation lives
under `backend_estadisticas.stats.track`.
"""
from importlib import import_module

try:
    _mod = import_module('backend_estadisticas.stats.track')
except Exception:
    # Fallback to the main views module when the dedicated subpackage is absent
    _mod = import_module('stats.views')

__all__ = [name for name in dir(_mod) if not name.startswith('_')]
globals().update({name: getattr(_mod, name) for name in __all__})
