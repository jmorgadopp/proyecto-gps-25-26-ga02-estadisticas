from django.db import models

class Playback(models.Model):
    song_id = models.CharField(max_length=64, db_index=True)
    played_at = models.DateTimeField(auto_now_add=True)
    seconds = models.PositiveIntegerField(default=0)
    valid = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["song_id", "played_at"])]
        ordering = ["-played_at"]

class AlbumSale(models.Model):
    album_id = models.CharField(max_length=64, db_index=True)
    purchased_at = models.DateTimeField(auto_now_add=True)
    units = models.PositiveIntegerField(default=1)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="EUR")
    refunded = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["album_id", "purchased_at"])]
        ordering = ["-purchased_at"]
