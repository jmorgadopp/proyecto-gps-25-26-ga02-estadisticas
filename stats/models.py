# stats/models.py
from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class Playback(models.Model):
    song_id = models.CharField(max_length=64, db_index=True)
    seconds = models.PositiveIntegerField(default=0)
    valid = models.BooleanField(default=True)
    played_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["song_id", "played_at"])]
        ordering = ["-played_at"]

    def __str__(self):
        return f"{self.song_id} · {self.seconds}s · {'valid' if self.valid else 'invalid'}"


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

    def __str__(self):
        flag = "REFUND" if self.refunded else "OK"
        return f"{self.album_id} · {self.units}u · {self.amount}{self.currency} · {flag}"


class Rating(models.Model):
    # Usuario que valora (soporta AUTH_USER_MODEL custom)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ratings",
    )
    # Identificadores funcionales
    song_id = models.CharField(max_length=64, db_index=True)
    artist_id = models.CharField(max_length=64, db_index=True, blank=True, null=True)

    # Puntuación 1..5
    stars = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.CharField(max_length=512, blank=True)
    rated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # 1 valoración por usuario y canción
        constraints = [
            models.UniqueConstraint(
                fields=["user", "song_id"], name="unique_rating_per_user_song"
            )
        ]
        indexes = [
            models.Index(fields=["song_id", "artist_id", "rated_at"]),
        ]
        ordering = ["-rated_at"]

    def __str__(self):
        return f"{self.user} → {self.song_id}: {self.stars}★"
