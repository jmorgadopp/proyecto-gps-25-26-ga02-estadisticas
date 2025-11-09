from django.urls import path
from .views import plays_by_song, sales_by_album

app_name = "stats"

urlpatterns = [
    path("api/v1/stats/songs/<str:song_id>/plays", plays_by_song, name="plays_by_song"),
    path("api/v1/stats/songs/<str:song_id>/plays/", plays_by_song),

    path("api/v1/stats/albums/<str:album_id>/sales", sales_by_album, name="sales_by_album"),
    path("api/v1/stats/albums/<str:album_id>/sales/", sales_by_album),
]
