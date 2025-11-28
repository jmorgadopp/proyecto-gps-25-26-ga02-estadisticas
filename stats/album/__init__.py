from importlib import import_module

# Re-export album helpers from local `stats.views` to keep compatibility.
_mod = import_module('stats.views')
__all__ = [name for name in dir(_mod) if not name.startswith('_')]
globals().update({name: getattr(_mod, name) for name in __all__})
