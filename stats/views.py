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
    # Si tienes utils con getters configurables
    from .utils import get_playback_model, get_album_sale_model, get_rating_model
except Exception:
    # Fallback a modelos locales
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


# ---------------------------------------------------------------------
# PLAYS POR CANCIÓN
# GET  -> devuelve el recuento
# POST -> inserta 1..N reproducciones y devuelve el nuevo total
#        (útil para probar el botón ▶ +1 del frontend)
# ---------------------------------------------------------------------
@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def plays_by_song(request, song_id: str):
    Playback = get_playback_model()

    if request.method == "POST":
        # Número de reproducciones a añadir (por defecto 1)
        try:
            count = int(request.data.get("count", 1))
            if count < 1:
                raise ValueError
        except Exception:
            return Response(
                {"detail": "El campo 'count' debe ser un entero >= 1."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Campos opcionales que soportamos si existen en el modelo
        valid_param = (str(request.data.get("valid", "true")) or "").lower()
        valid_value = True if valid_param in TRUTHY else False if valid_param in FALSY else True

        played_at_raw = request.data.get("played_at")
        played_at_value = parse_datetime(played_at_raw) if played_at_raw else None
        if played_at_value is None:
            played_at_value = timezone.now()

        artist_id_value = request.data.get("artist_id")
        label_id_value = request.data.get("label_id")

        # Construimos kwargs respetando sólo los campos existentes
        base_kwargs = {"song_id": str(song_id)}
        if has_field(Playback, "valid"):
            base_kwargs["valid"] = valid_value
        if has_field(Playback, "played_at"):
            base_kwargs["played_at"] = played_at_value
        if artist_id_value and has_field(Playback, "artist_id"):
            base_kwargs["artist_id"] = artist_id_value
        if label_id_value and has_field(Playback, "label_id"):
            base_kwargs["label_id"] = label_id_value

        # Inserción (bulk si count>1)
        if count == 1:
            Playback.objects.create(**base_kwargs)
        else:
            Playback.objects.bulk_create([Playback(**base_kwargs) for _ in range(count)])

        # Nuevo total tras insertar
        new_total = Playback.objects.filter(song_id=str(song_id)).count()
        return Response(
            {"ok": True, "song_id": str(song_id), "added": count, "total": new_total},
            status=status.HTTP_201_CREATED,
        )

    # --- GET: filtros y recuento ---
    qs = Playback.objects.filter(song_id=str(song_id))

    v = (request.query_params.get("valid") or "").lower()
    if v in TRUTHY:
        qs = qs.filter(valid=True)
    elif v in FALSY:
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

    return Response({"song_id": str(song_id), "plays": qs.count()})


@api_view(["GET"])
@permission_classes([AllowAny])
def sales_by_album(request, album_id: str):
    AlbumSale = get_album_sale_model()
    qs = AlbumSale.objects.filter(album_id=album_id)

    if (request.query_params.get("include_refunds") or "").lower() not in TRUTHY:
        qs = qs.filter(refunded=False)

    f = request.query_params.get("from")
    t = request.query_params.get("to")
    if f:
        dt = parse_datetime(f)
        if dt:
            qs = qs.filter(purchased_at__gte=dt)
    if t:
        dt = parse_datetime(t)
        if dt:
            qs = qs.filter(purchased_at__lte=dt)

    orders = qs.count()
    units = qs.aggregate(total=Sum("units"))["total"] or 0
    resp = {"album_id": album_id, "orders": orders, "sales": units}

    if (request.query_params.get("revenue") or "").lower() in TRUTHY:
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

    # Filtros por label / artistas si los campos existen
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

    # Ventanas temporales
    f = request.query_params.get("from")
    t = request.query_params.get("to")
    if f:
        dt = parse_datetime(f)
        if dt:
            plays_qs = plays_qs.filter(played_at__gte=dt)
            sales_qs = sales_qs.filter(purchased_at__gte=dt)
            if rate_qs is not None:
                rate_qs = rate_qs.filter(rated_at__gte=dt)
    if t:
        dt = parse_datetime(t)
        if dt:
            plays_qs = plays_qs.filter(played_at__lte=dt)
            sales_qs = sales_qs.filter(purchased_at__lte=dt)
            if rate_qs is not None:
                rate_qs = rate_qs.filter(rated_at__lte=dt)

    # Plays válidas opcional
    v = (request.query_params.get("valid") or "").lower()
    if v in TRUTHY:
        plays_qs = plays_qs.filter(valid=True)
    elif v in FALSY:
        plays_qs = plays_qs.filter(valid=False)

    plays_total = plays_qs.count()
    plays_valid = Playback.objects.filter(pk__in=plays_qs.values("pk"), valid=True).count()

    # Ventas (sin refund por defecto)
    if (request.query_params.get("include_refunds") or "").lower() not in TRUTHY:
        sales_qs = sales_qs.filter(refunded=False)
    orders = sales_qs.count()
    units = sales_qs.aggregate(total=Sum("units"))["total"] or 0

    # Ratings
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

    if (request.query_params.get("revenue") or "").lower() in TRUTHY:
        revenue = sales_qs.aggregate(total=Sum("amount"))["total"] or 0
        resp["sales"]["revenue"] = str(revenue)

    # Agrupación por artista (si existe el campo)
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
                "sales_orders": 0,
                "sales_units": 0,
                "revenue": None,
                "ratings_count": 0,
                "ratings_average": None,
            }

        if has_field(AlbumSale, "artist_id"):
            agg_s = sales_qs.values("artist_id").annotate(
                sales_orders=Count("id"),
                sales_units=Sum("units"),
                revenue=Sum("amount"),
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
                cur["revenue"] = str(row["revenue"] or 0)

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

    # Autenticación: en DEBUG aceptamos cabecera X-Dev-User
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
        "rated_at": obj.rated_at,
        "created": created,
    }
    return Response(payload, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
