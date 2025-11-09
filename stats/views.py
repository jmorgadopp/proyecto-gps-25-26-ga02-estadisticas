from django.utils.dateparse import parse_datetime
from django.db.models import Sum, Count, Case, When, IntegerField
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

# Capa de compatibilidad: usamos utils si existe; si no, caemos al modelo local.
try:
    from .utils import get_playback_model, get_album_sale_model, get_rating_model
except Exception:
    from .models import Playback as _Playback, AlbumSale as _AlbumSale
    try:
        from .models import Rating as _Rating
    except Exception:
        _Rating = None
    def get_playback_model(): return _Playback
    def get_album_sale_model(): return _AlbumSale
    def get_rating_model(): return _Rating

TRUTHY = {"1", "true", "yes", "y", "t"}
FALSY  = {"0", "false", "no", "n", "f"}

def has_field(model, name: str) -> bool:
    return model is not None and any(f.name == name for f in model._meta.get_fields())

# ----------------- ENDPOINTS -----------------

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
        dt = parse_datetime(f)
        if dt: qs = qs.filter(played_at__gte=dt)
    if t:
        dt = parse_datetime(t)
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
        dt = parse_datetime(f)
        if dt: qs = qs.filter(purchased_at__gte=dt)
    if t:
        dt = parse_datetime(t)
        if dt: qs = qs.filter(purchased_at__lte=dt)

    orders = qs.count()
    units  = qs.aggregate(total=Sum("units"))["total"] or 0
    resp = {"album_id": album_id, "orders": orders, "sales": units}

    if (request.query_params.get("revenue") or "").lower() in TRUTHY:
        revenue = qs.aggregate(total=Sum("amount"))["total"] or 0
        resp["revenue"] = str(revenue)

    return Response(resp)


@api_view(["GET"])
@permission_classes([AllowAny])
def global_stats(request):
    Playback  = get_playback_model()
    AlbumSale = get_album_sale_model()
    Rating    = get_rating_model()

    plays_qs = Playback.objects.all()
    sales_qs = AlbumSale.objects.all()
    rate_qs  = Rating.objects.all() if Rating is not None else None

    # filtros tiempo
    f = request.query_params.get("from"); t = request.query_params.get("to")
    if f:
        dt = parse_datetime(f)
        if dt:
            plays_qs = plays_qs.filter(played_at__gte=dt)
            sales_qs = sales_qs.filter(purchased_at__gte=dt)
            if rate_qs is not None: rate_qs = rate_qs.filter(rated_at__gte=dt)
    if t:
        dt = parse_datetime(t)
        if dt:
            plays_qs = plays_qs.filter(played_at__lte=dt)
            sales_qs = sales_qs.filter(purchased_at__lte=dt)
            if rate_qs is not None: rate_qs = rate_qs.filter(rated_at__lte=dt)

    # plays válidas opcional
    v = (request.query_params.get("valid") or "").lower()
    if v in TRUTHY: plays_qs = plays_qs.filter(valid=True)
    elif v in FALSY: plays_qs = plays_qs.filter(valid=False)

    plays_total = plays_qs.count()
    plays_valid = Playback.objects.filter(pk__in=plays_qs.values("pk"), valid=True).count()

    # ventas (refunds)
    if (request.query_params.get("include_refunds") or "").lower() not in TRUTHY:
        sales_qs = sales_qs.filter(refunded=False)
    orders = sales_qs.count()
    units  = sales_qs.aggregate(total=Sum("units"))["total"] or 0

    # valoraciones (si existe el modelo)
    ratings_count = 0
    ratings_avg = None
    if rate_qs is not None:
        from django.db.models import Avg
        ratings_count = rate_qs.count()
        ratings_avg = rate_qs.aggregate(avg=Avg("stars"))["avg"]

    resp = {
        "timeframe": {"from": f, "to": t},
        "plays":   {"total": plays_total, "valid": plays_valid},
        "sales":   {"orders": orders, "units": units},
        "ratings": {"count": ratings_count, "average": round(float(ratings_avg), 2) if ratings_avg is not None else None},
    }

    if (request.query_params.get("revenue") or "").lower() in TRUTHY:
        revenue = sales_qs.aggregate(total=Sum("amount"))["total"] or 0
        resp["sales"]["revenue"] = str(revenue)

    # agrupación por artista (solo si los modelos tienen artist_id)
    if (request.query_params.get("group_by") or "").lower() == "artist" and has_field(Playback, "artist_id"):
        by_artist = {}

        agg_p = plays_qs.values("artist_id").annotate(
            plays_total=Count("id"),
            plays_valid=Sum(Case(When(valid=True, then=1), default=0, output_field=IntegerField())),
        )
        for row in agg_p:
            by_artist[row["artist_id"]] = {
                "artist_id": row["artist_id"],
                "plays_total": row["plays_total"],
                "plays_valid": row["plays_valid"],
                "sales_orders": 0, "sales_units": 0, "revenue": None,
                "ratings_count": 0, "ratings_average": None,
            }

        if has_field(AlbumSale, "artist_id"):
            agg_s = sales_qs.values("artist_id").annotate(
                sales_orders=Count("id"),
                sales_units=Sum("units"),
                revenue=Sum("amount"),
            )
            for row in agg_s:
                cur = by_artist.setdefault(row["artist_id"], {
                    "artist_id": row["artist_id"], "plays_total": 0, "plays_valid": 0,
                    "sales_orders": 0, "sales_units": 0, "revenue": None,
                    "ratings_count": 0, "ratings_average": None,
                })
                cur["sales_orders"] = row["sales_orders"] or 0
                cur["sales_units"]  = row["sales_units"]  or 0
                cur["revenue"]      = str(row["revenue"] or 0)

        if rate_qs is not None and has_field(get_rating_model(), "artist_id"):
            from django.db.models import Avg
            agg_r = rate_qs.values("artist_id").annotate(
                ratings_count=Count("id"),
                ratings_average=Avg("stars"),
            )
            for row in agg_r:
                cur = by_artist.setdefault(row["artist_id"], {
                    "artist_id": row["artist_id"], "plays_total": 0, "plays_valid": 0,
                    "sales_orders": 0, "sales_units": 0, "revenue": None,
                    "ratings_count": 0, "ratings_average": None,
                })
                cur["ratings_count"]   = row["ratings_count"] or 0
                cur["ratings_average"] = round(float(row["ratings_average"]), 2) if row["ratings_average"] else None

        resp["by_artist"] = list(by_artist.values())

    return Response(resp)
