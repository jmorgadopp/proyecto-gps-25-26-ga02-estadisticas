# stats/views.py
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.db.models import Sum, Count, Case, When, IntegerField, Avg

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .permissions import IsDiscografica

# ---------- Compatibilidad para obtener modelos ----------
try:
    from .utils import get_playback_model, get_album_sale_model, get_rating_model
except Exception:
    from .models import Playback as _Playback, AlbumSale as _AlbumSale
    try:
        from .models import Rating as _Rating
    except Exception:
        _Rating = None

    def get_playback_model():
        return _Playback

    def get_album_sale_model():
        return _AlbumSale

    def get_rating_model():
        return _Rating
# --------------------------------------------------------

TRUTHY = {"1", "true", "yes", "y", "t"}
FALSY = {"0", "false", "no", "n", "f"}


def has_field(model, name: str) -> bool:
    return model is not None and any(f.name == name for f in model._meta.get_fields())


@api_view(["GET", "POST", "DELETE"])
@permission_classes([AllowAny])  # en DEBUG permitimos pruebas sin auth
def plays_by_song(request, song_id: str):
    """
    GET     -> devuelve {"song_id":..., "plays": N} con filtros opcionales.
    POST    -> inserta 1 reproducción para song_id y devuelve el nuevo total.
    DELETE  -> elimina la reproducción más reciente (si existe) y devuelve el nuevo total.
    """
    Playback = get_playback_model()

    if request.method == "POST":
        # Crear una reproducción "válida" ahora
        obj = Playback.objects.create(
            song_id=song_id,
            valid=True if has_field(Playback, "valid") else True,
            played_at=timezone.now() if has_field(Playback, "played_at") else None,
        )
        # Si algún campo no existe, create() lo ignorará si no se pasa
        total = Playback.objects.filter(song_id=song_id).count()
        return Response({"song_id": song_id, "plays": total, "changed": +1}, status=201)

    if request.method == "DELETE":
        # Eliminar la más reciente si tenemos timestamp, si no por id
        qs = Playback.objects.filter(song_id=song_id)
        if has_field(Playback, "played_at"):
            qs = qs.order_by("-played_at")
        else:
            qs = qs.order_by("-id")
        last = qs.first()
        if last:
            last.delete()
        total = Playback.objects.filter(song_id=song_id).count()
        return Response({"song_id": song_id, "plays": total, "changed": -1})

    # --- GET ---
    qs = Playback.objects.filter(song_id=song_id)

    v = (request.query_params.get("valid") or "").lower()
    if v in TRUTHY:
        if has_field(Playback, "valid"):
            qs = qs.filter(valid=True)
    elif v in FALSY:
        if has_field(Playback, "valid"):
            qs = qs.filter(valid=False)

    f = request.query_params.get("from")
    t = request.query_params.get("to")
    if f:
        dt = parse_datetime(f)
        if dt and has_field(Playback, "played_at"):
            qs = qs.filter(played_at__gte=dt)
    if t:
        dt = parse_datetime(t)
        if dt and has_field(Playback, "played_at"):
            qs = qs.filter(played_at__lte=dt)

    return Response({"song_id": song_id, "plays": qs.count()})


@api_view(["GET"])
@permission_classes([AllowAny])
def sales_by_album(request, album_id: str):
    AlbumSale = get_album_sale_model()
    qs = AlbumSale.objects.filter(album_id=album_id)

    if (request.query_params.get("include_refunds") or "").lower() not in TRUTHY:
        if has_field(AlbumSale, "refunded"):
            qs = qs.filter(refunded=False)

    f = request.query_params.get("from")
    t = request.query_params.get("to")
    if f:
        dt = parse_datetime(f)
        if dt and has_field(AlbumSale, "purchased_at"):
            qs = qs.filter(purchased_at__gte=dt)
    if t:
        dt = parse_datetime(t)
        if dt and has_field(AlbumSale, "purchased_at"):
            qs = qs.filter(purchased_at__lte=dt)

    orders = qs.count()
    units = qs.aggregate(total=Sum("units"))["total"] or 0
    resp = {"album_id": album_id, "orders": orders, "sales": units}

    if (request.query_params.get("revenue") or "").lower() in TRUTHY and has_field(AlbumSale, "amount"):
        revenue = qs.aggregate(total=Sum("amount"))["total"] or 0
        resp["revenue"] = str(revenue)

    return Response(resp)


@api_view(["GET"])
@permission_classes([IsDiscografica])
def global_stats(request):
    Playback = get_playback_model()
    AlbumSale = get_album_sale_model()
    Rating = get_rating_model()

    plays_qs = Playback.objects.all()
    sales_qs = AlbumSale.objects.all()
    rate_qs = Rating.objects.all() if Rating is not None else None

    label_id = request.query_params.get("label_id")
    if label_id:
        if has_field(Playback, "label_id"):
            plays_qs = plays_qs.filter(label_id=label_id)
        if has_field(AlbumSale, "label_id"):
            sales_qs = sales_qs.filter(label_id=label_id)
        if rate_qs is not None and has_field(Rating, "label_id"):
            rate_qs = rate_qs.filter(label_id=label_id)

    artists_csv = request.query_params.get("artists")
    if artists_csv:
        ids = [a.strip() for a in artists_csv.split(",") if a.strip()]
        if has_field(Playback, "artist_id"):
            plays_qs = plays_qs.filter(artist_id__in=ids)
        if has_field(AlbumSale, "artist_id"):
            sales_qs = sales_qs.filter(artist_id__in=ids)
        if rate_qs is not None and has_field(Rating, "artist_id"):
            rate_qs = rate_qs.filter(artist_id__in=ids)

    f = request.query_params.get("from")
    t = request.query_params.get("to")
    if f:
        dt = parse_datetime(f)
        if dt:
            if has_field(Playback, "played_at"):
                plays_qs = plays_qs.filter(played_at__gte=dt)
            if has_field(AlbumSale, "purchased_at"):
                sales_qs = sales_qs.filter(purchased_at__gte=dt)
            if rate_qs is not None and has_field(Rating, "rated_at"):
                rate_qs = rate_qs.filter(rated_at__gte=dt)
    if t:
        dt = parse_datetime(t)
        if dt:
            if has_field(Playback, "played_at"):
                plays_qs = plays_qs.filter(played_at__lte=dt)
            if has_field(AlbumSale, "purchased_at"):
                sales_qs = sales_qs.filter(purchased_at__lte=dt)
            if rate_qs is not None and has_field(Rating, "rated_at"):
                rate_qs = rate_qs.filter(rated_at__lte=dt)

    v = (request.query_params.get("valid") or "").lower()
    if v in TRUTHY and has_field(Playback, "valid"):
        plays_qs = plays_qs.filter(valid=True)
    elif v in FALSY and has_field(Playback, "valid"):
        plays_qs = plays_qs.filter(valid=False)

    plays_total = plays_qs.count()
    plays_valid = Playback.objects.filter(pk__in=plays_qs.values("pk"), **({"valid": True} if has_field(Playback, "valid") else {})).count()

    if (request.query_params.get("include_refunds") or "").lower() not in TRUTHY and has_field(get_album_sale_model(), "refunded"):
        sales_qs = sales_qs.filter(refunded=False)
    orders = sales_qs.count()
    units = sales_qs.aggregate(total=Sum("units"))["total"] or 0

    ratings_count = 0
    ratings_avg = None
    if rate_qs is not None:
        ratings_count = rate_qs.count()
        ratings_avg = rate_qs.aggregate(avg=Avg("stars"))["avg"]

    resp = {
        "timeframe": {"from": f, "to": t},
        "plays": {"total": plays_total, "valid": plays_valid},
        "sales": {"orders": orders, "units": units},
        "ratings": {
            "count": ratings_count,
            "average": round(float(ratings_avg), 2) if ratings_avg is not None else None,
        },
    }

    if (request.query_params.get("revenue") or "").lower() in TRUTHY and has_field(get_album_sale_model(), "amount"):
        revenue = sales_qs.aggregate(total=Sum("amount"))["total"] or 0
        resp["sales"]["revenue"] = str(revenue)

    if (request.query_params.get("group_by") or "").lower() == "artist" and has_field(Playback, "artist_id"):
        by_artist = {}

        agg_p = plays_qs.values("artist_id").annotate(
            plays_total=Count("id"),
            plays_valid=Sum(Case(When(valid=True, then=1), default=0, output_field=IntegerField())) if has_field(Playback, "valid") else Count("id"),
        )
        for row in agg_p:
            by_artist[row["artist_id"]] = {
                "artist_id": row["artist_id"],
                "plays_total": row["plays_total"],
                "plays_valid": row.get("plays_valid", row["plays_total"]),
                "sales_orders": 0,
                "sales_units": 0,
                "revenue": None,
                "ratings_count": 0,
                "ratings_average": None,
            }

        AlbumSale = get_album_sale_model()
        if has_field(AlbumSale, "artist_id"):
            agg_s = sales_qs.values("artist_id").annotate(
                sales_orders=Count("id"),
                sales_units=Sum("units"),
                revenue=Sum("amount") if has_field(AlbumSale, "amount") else None,
            )
            for row in agg_s:
                cur = by_artist.setdefault(
                    row["artist_id"],
                    {
                        "artist_id": row["artist_id"],
                        "plays_total": 0,
                        "plays_valid": 0,
                        "sales_orders": 0,
                        "sales_units": 0,
                        "revenue": None,
                        "ratings_count": 0,
                        "ratings_average": None,
                    },
                )
                cur["sales_orders"] = row["sales_orders"] or 0
                cur["sales_units"] = row["sales_units"] or 0
                cur["revenue"] = str(row.get("revenue") or 0) if "revenue" in row else None

        rating_model = get_rating_model()
        if rate_qs is not None and has_field(rating_model, "artist_id"):
            agg_r = rate_qs.values("artist_id").annotate(
                ratings_count=Count("id"),
                ratings_average=Avg("stars"),
            )
            for row in agg_r:
                cur = by_artist.setdefault(
                    row["artist_id"],
                    {
                        "artist_id": row["artist_id"],
                        "plays_total": 0,
                        "plays_valid": 0,
                        "sales_orders": 0,
                        "sales_units": 0,
                        "revenue": None,
                        "ratings_count": 0,
                        "ratings_average": None,
                    },
                )
                cur["ratings_count"] = row["ratings_count"] or 0
                cur["ratings_average"] = (
                    round(float(row["ratings_average"]), 2) if row["ratings_average"] else None
                )

        resp["by_artist"] = list(by_artist.values())

    return Response(resp)


@api_view(["GET", "POST", "PUT", "DELETE"])
@permission_classes([AllowAny])  # lectura pública; escritura requiere auth o cabecera DEV
def rating_for_song(request, song_id: str):
    Rating = get_rating_model()

    if request.method == "GET":
        qs = Rating.objects.filter(song_id=song_id)
        agg = qs.aggregate(a=Avg("stars"))
        data = {
            "song_id": song_id,
            "count": qs.count(),
            "average": round(float(agg["a"]), 2) if agg["a"] is not None else None,
            "user_rating": None,
        }
        if getattr(request, "user", None) and request.user.is_authenticated:
            mine = qs.filter(user=request.user).first()
            data["user_rating"] = getattr(mine, "stars", None)
        return Response(data)

    if (not getattr(request, "user", None) or not request.user.is_authenticated) and settings.DEBUG:
        dev_user = request.headers.get("X-Dev-User") or request.META.get("HTTP_X_DEV_USER")
        if dev_user:
            User = get_user_model()
            try:
                request.user = User.objects.get(username=dev_user)
            except User.DoesNotExist:
                return Response({"detail": "X-Dev-User not found."}, status=status.HTTP_401_UNAUTHORIZED)

    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

    if request.method == "DELETE":
        Rating.objects.filter(user=request.user, song_id=song_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    stars = request.data.get("stars")
    comment = request.data.get("comment", "")

    try:
        stars = int(stars)
        if not (1 <= stars <= 5):
            raise ValueError
    except Exception:
        return Response(
            {"detail": "Field 'stars' must be an integer between 1 and 5."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    obj, created = Rating.objects.update_or_create(
        user=request.user,
        song_id=song_id,
        defaults={"stars": stars, "comment": comment},
    )

    payload = {
        "song_id": song_id,
        "stars": obj.stars,
        "comment": obj.comment,
        "rated_at": getattr(obj, "rated_at", None),
        "created": created,
    }
    return Response(payload, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
