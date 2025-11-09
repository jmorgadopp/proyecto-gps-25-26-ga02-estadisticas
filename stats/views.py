from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import Playback

@api_view(["GET"])
@permission_classes([AllowAny])
def plays_by_song(request, song_id: str):
    qs = Playback.objects.filter(song_id=song_id)

    v = request.query_params.get("valid")
    if v is not None:
        v = v.lower()
        if v in {"1", "true", "yes", "t"}:
            qs = qs.filter(valid=True)
        elif v in {"0", "false", "no", "f"}:
            qs = qs.filter(valid=False)

    f = request.query_params.get("from")
    t = request.query_params.get("to")
    if f:
        dt = parse_datetime(f)
        if dt:
            qs = qs.filter(played_at__gte=dt)
    if t:
        dt = parse_datetime(t)
        if dt:
            qs = qs.filter(played_at__lte=dt)

    return Response({"song_id": song_id, "plays": qs.count()})
