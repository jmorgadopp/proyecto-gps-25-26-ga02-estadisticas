Backend reorganized layout for `estadisticas` service.

Structure created:

- `backend_estadisticas/stats/` — compatibility package that re-exports
  modules from the existing top-level `stats` package.
- `backend_estadisticas/stats/album` — placeholder for album-related modules.
- `backend_estadisticas/stats/artist` — placeholder for artist-related modules.
- `backend_estadisticas/stats/track` — placeholder for track-related modules.
- `backend_estadisticas/stats/record_label` — placeholder for label-specific code.
- `backend_estadisticas/stats/rating` — placeholder for rating-specific code.

Notes:

1. To keep risk minimal and preserve database migrations and app registration
   the Django app package `stats` is unchanged. The new package only provides
   a clearer place for future re-organization and a compatibility layer so
   code can import `backend_estadisticas.stats.*` while the running app still
   uses `stats`.

2. If you prefer a full migration (move `stats` app into `backend_estadisticas/stats`
   and update `INSTALLED_APPS` accordingly) I can perform that in a follow-up
   change — it requires updating migrations/app paths or adding migration
   adjustments.
