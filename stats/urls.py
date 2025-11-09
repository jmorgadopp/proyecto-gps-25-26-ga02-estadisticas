from django.urls import path
from .views import plays_by_song

urlpatterns = [
    path("api/v1/stats/songs/<str:song_id>/plays", plays_by_song, name="plays_by_song"),
    path("api/v1/stats/songs/<str:song_id>/plays/", plays_by_song),  # opcional, por comodidad
]
