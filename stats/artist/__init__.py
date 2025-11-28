from importlib import import_module

# Expose symbols from the local `stats.views` module so callers importing
# `stats.artist` keep working after consolidation.
_mod = import_module('stats.views')
__all__ = [name for name in dir(_mod) if not name.startswith('_')]
globals().update({name: getattr(_mod, name) for name in __all__})
