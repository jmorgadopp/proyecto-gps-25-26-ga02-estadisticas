"""Shim urls that delegate to the reorganized package.

Keeping `stats.urls` importable so `include('stats.urls')` continues
to work while the actual implementation is under
`backend_estadisticas.stats.urls`.
"""
from django.urls import path
from . import views as stats_views

app_name = "stats"

urlpatterns = [
	path("api/v1/stats/songs/<str:song_id>/plays", stats_views.plays_by_song),
	path("api/v1/stats/songs/<str:song_id>/plays/", stats_views.plays_by_song),

	path("api/v1/stats/albums/<str:album_id>/sales", stats_views.sales_by_album),
	path("api/v1/stats/albums/<str:album_id>/sales/", stats_views.sales_by_album),

	path("api/v1/stats/artists", stats_views.artists_stats),
	path("api/v1/stats/artists/", stats_views.artists_stats),
	path("api/v1/stats/artists/ratings", stats_views.artists_ratings),
	path("api/v1/stats/artists/ratings/", stats_views.artists_ratings),
	path("api/v1/stats/artists/aggregate", stats_views.artists_aggregate),
	path("api/v1/stats/artists/aggregate/", stats_views.artists_aggregate),
	path("api/v1/stats/artists/<str:artist_id>/aggregate", stats_views.artist_aggregate),
	path("api/v1/stats/artists/<str:artist_id>/aggregate/", stats_views.artist_aggregate),
	# Alias using camelCase for frontend convenience/backwards compatibility
	path("api/v1/stats/artists/<str:artist_id>/artistAggregate", stats_views.artist_aggregate),
	path("api/v1/stats/artists/<str:artist_id>/artistAggregate/", stats_views.artist_aggregate),

	path("api/v1/stats/global", stats_views.global_stats),
	path("api/v1/stats/global/", stats_views.global_stats),

	# Individual ratings list/create and detail
	path("api/v1/stats/songs/<str:song_id>/ratings/", stats_views.SongRatingsListCreateView.as_view()),
	path("api/v1/stats/songs/<str:song_id>/ratings", stats_views.SongRatingsListCreateView.as_view()),
	# New song-level aggregate endpoint (camelCase alias too)
	path("api/v1/stats/songs/<str:song_id>/aggregate", stats_views.song_aggregate),
	path("api/v1/stats/songs/<str:song_id>/aggregate/", stats_views.song_aggregate),
	path("api/v1/stats/songs/<str:song_id>/songAggregate", stats_views.song_aggregate),
	path("api/v1/stats/songs/<str:song_id>/songAggregate/", stats_views.song_aggregate),
	# Compatibility: singular rating endpoint used by older frontend code
	path("api/v1/stats/songs/<str:song_id>/rating", stats_views.rating_by_song),
	path("api/v1/stats/songs/<str:song_id>/rating/", stats_views.rating_by_song),
	# Back-compat: allow fetching a specific rating under the song path
	path("api/v1/stats/songs/<str:song_id>/rating/<int:pk>", stats_views.RatingDetailView.as_view()),
	path("api/v1/stats/songs/<str:song_id>/rating/<int:pk>/", stats_views.RatingDetailView.as_view()),
	path("api/v1/stats/ratings/<int:pk>/", stats_views.RatingDetailView.as_view()),
	path("api/v1/stats/ratings/<int:pk>", stats_views.RatingDetailView.as_view()),
]

app_name = "stats"

