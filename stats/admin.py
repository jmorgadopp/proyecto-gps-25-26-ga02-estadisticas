from django.contrib import admin
from .models import Rating

@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ("user", "song_id", "artist_id", "stars", "rated_at")
    list_filter = ("stars",)
    search_fields = ("song_id", "artist_id", "user__username", "user__email")
