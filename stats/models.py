from django.db import models

class Playback(models.Model):
    song_id = models.CharField(max_length=64, db_index=True)
    played_at = models.DateTimeField(auto_now_add=True)
    seconds = models.PositiveIntegerField(default=0)
    valid = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["song_id", "played_at"])]
        ordering = ["-played_at"]

    def __str__(self):
        return f"{self.song_id} @ {self.played_at:%Y-%m-%d %H:%M:%S}"
