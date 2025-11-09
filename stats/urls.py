from django.urls import path
from . import views as stats_views

app_name = "stats"

urlpatterns = [
    path("api/v1/stats/songs/<str:song_id>/plays", stats_views.plays_by_song),
    path("api/v1/stats/songs/<str:song_id>/plays/", stats_views.plays_by_song),

    path("api/v1/stats/albums/<str:album_id>/sales", stats_views.sales_by_album),
    path("api/v1/stats/albums/<str:album_id>/sales/", stats_views.sales_by_album),

    path("api/v1/stats/global", stats_views.global_stats),
    path("api/v1/stats/global/", stats_views.global_stats),

# Ratings: GET/POST/PUT/DELETE
    path("api/v1/stats/songs/<str:song_id>/rating",  stats_views.rating_for_song),
    path("api/v1/stats/songs/<str:song_id>/rating/", stats_views.rating_for_song),
]
