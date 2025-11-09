from django.conf import settings
from django.apps import apps as dj_apps

def _get_model(setting_name: str, default_label: str):
    label = getattr(settings, setting_name, default_label)
    return dj_apps.get_model(label, require_ready=False)

def get_playback_model():
    return _get_model("STATS_PLAYBACK_MODEL", "stats.Playback")

def get_album_sale_model():
    return _get_model("STATS_ALBUM_SALE_MODEL", "stats.AlbumSale")
