"""Top-level package for reorganized backend code.

This package is a lightweight container to group backend code under
`backend_estadisticas/`. It provides no runtime behavior by itself —
individual apps live in the top-level `stats` package (kept for
compatibility with Django's INSTALLED_APPS). This package contains
shims and documentation to ease a later migration.
"""

__all__ = ["stats"]

# Keep `backend_estadisticas.stats` package for backwards compatibility
# but prefer importing from top-level `stats` after consolidation.
try:
	# Attempt to make `backend_estadisticas.stats` importable by delegating
	# to the top-level `stats` package when present.
	import importlib
	importlib.invalidate_caches()
	import types
	from importlib import import_module
	try:
		_stats = import_module('stats')
		import sys
		sys.modules['backend_estadisticas.stats'] = _stats
	except Exception:
		# If `stats` is not importable yet, leave the package as-is.
		pass
except Exception:
	pass
