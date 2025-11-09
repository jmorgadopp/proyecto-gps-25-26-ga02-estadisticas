from django.utils.dateparse import parse_datetime
from django.db.models import Sum
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .utils import get_playback_model, get_album_sale_model

TRUTHY = {"1", "true", "yes", "y", "t"}
FALSY  = {"0", "false", "no", "n", "f"}

@api_view(["GET"])
@permission_classes([AllowAny])
def plays_by_song(request, song_id: str):
    Playback = get_playback_model()
    qs = Playback.objects.filter(song_id=song_id)

    v = (request.query_params.get("valid") or "").lower()
    if v in TRUTHY: qs = qs.filter(valid=True)
    elif v in FALSY: qs = qs.filter(valid=False)

    f = request.query_params.get("from"); t = request.query_params.get("to")
    if f:
        dt = parse_datetime(f);
        if dt: qs = qs.filter(played_at__gte=dt)
    if t:
        dt = parse_datetime(t);
        if dt: qs = qs.filter(played_at__lte=dt)

    return Response({"song_id": song_id, "plays": qs.count()})

@api_view(["GET"])
@permission_classes([AllowAny])
def sales_by_album(request, album_id: str):
    AlbumSale = get_album_sale_model()
    qs = AlbumSale.objects.filter(album_id=album_id)

    if (request.query_params.get("include_refunds") or "").lower() not in TRUTHY:
        qs = qs.filter(refunded=False)

    f = request.query_params.get("from"); t = request.query_params.get("to")
    if f:
        dt = parse_datetime(f);
        if dt: qs = qs.filter(purchased_at__gte=dt)
    if t:
        dt = parse_datetime(t);
        if dt: qs = qs.filter(purchased_at__lte=dt)

    orders = qs.count()
    units = qs.aggregate(total=Sum("units"))["total"] or 0
    resp = {"album_id": album_id, "orders": orders, "sales": units}

    if (request.query_params.get("revenue") or "").lower() in TRUTHY:
        revenue = qs.aggregate(total=Sum("amount"))["total"] or 0
        resp["revenue"] = str(revenue)

    return Response(resp)
