# stats/views.py
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.db.models import Sum, Count, Case, When, IntegerField, Avg
from django.core.exceptions import FieldError

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .permissions import IsDiscografica
import requests
from django.conf import settings

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


def _fetch_artists_meta_by_ids(ids_csv: str):
    """Try bulk fetch from contenidos; if returned set is incomplete, fall back to per-id fetch.

    Returns dict mapping id -> normalized artist object {id, name, ...}
    """
    meta = {}
    if not ids_csv:
        return meta
    content_api = getattr(settings, "CONTENT_API_BASE", "http://127.0.0.1:8001/api/v1")
    try:
        r = requests.get(f"{content_api}/artists?ids={ids_csv}", timeout=5)
        if r.ok:
            try:
                resp = r.json()
            except Exception:
                resp = None

            artists_list = []
            if isinstance(resp, list):
                artists_list = resp
            elif isinstance(resp, dict):
                artists_list = resp.get("items") or resp.get("artists") or []

            for a in artists_list:
                if not a:
                    continue
                key = a.get("id") or a.get("artist_id") or a.get("artistId") or a.get("uuid")
                if key:
                    meta[str(key)] = {"id": str(key), "name": a.get("name") or a.get("artist_name") or a.get("title"), **a}

        # detect missing ids and fetch individually
        requested = [s.strip() for s in ids_csv.split(",") if s.strip()]
        missing = [mid for mid in requested if mid not in meta]
        for mid in missing:
            try:
                r2 = requests.get(f"{content_api}/artists/{mid}", timeout=4)
                if r2.ok:
                    a = r2.json()
                    if a:
                        key = a.get("id") or a.get("artist_id") or a.get("uuid") or mid
                        meta[str(key)] = {"id": str(key), "name": a.get("name") or a.get("artist_name") or a.get("title"), **a}
            except Exception:
                # ignore individual fetch failures
                continue
    except Exception:
        # on any failure, return whatever we managed to collect (possibly empty)
        return meta

    return meta


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
        # try to get label_id from request data or headers
        label = request.data.get("label_id") or request.headers.get("X-Label-Id") or request.META.get("HTTP_X_LABEL_ID")

        # If label_id is not provided but the Playback model has no label yet,
        # try to resolve it by querying the contenidos service for the track
        if not label and has_field(Playback, "label_id"):
            try:
                content_api = getattr(settings, "CONTENT_API_BASE", "http://127.0.0.1:8001/api/v1")
                url = f"{content_api}/tracks/{song_id}"
                r = requests.get(url, timeout=2)
                if r.ok:
                    data = r.json()
                    # Track serializer includes nested artist with label info if available
                    artist = data.get("artist") or {}
                    # artist may include label_id
                    label = artist.get("label_id") or artist.get("label", {}).get("label_id")
            except Exception:
                label = None

        obj_kwargs = {"song_id": song_id}
        if has_field(Playback, "valid"):
            obj_kwargs["valid"] = True
        if has_field(Playback, "played_at"):
            obj_kwargs["played_at"] = timezone.now()
        if has_field(Playback, "label_id") and label:
            obj_kwargs["label_id"] = label

        obj = Playback.objects.create(**obj_kwargs)
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


@api_view(["GET"])
@permission_classes([IsDiscografica])
def artists_stats(request):
    """Return aggregated metrics per artist.

    Query params:
    - `limit` (int): number of artists to return (default 20)
    - `offset` (int): pagination offset (default 0)
    - `sort` (plays|sales|ratings) default 'plays' (desc)
    - `from`, `to`, `valid` and `include_refunds` same as `global_stats`
    - `enrich` (1|true) if present will call contenidos to get artist metadata
    """
    Playback = get_playback_model()
    AlbumSale = get_album_sale_model()
    Rating = get_rating_model()

    plays_qs = Playback.objects.all()
    sales_qs = AlbumSale.objects.all()
    rate_qs = Rating.objects.all() if Rating is not None else None

    # Ensure we have at least one artist_id field available
    if not (has_field(Playback, "artist_id") or has_field(AlbumSale, "artist_id") or (rate_qs is not None and has_field(Rating, "artist_id"))):
        return Response({"detail": "No artist_id field available on models to aggregate by artist."}, status=400)

    f = request.query_params.get("from")
    t = request.query_params.get("to")
    if f:
        dt = parse_datetime(f)
        if dt and has_field(Playback, "played_at"):
            plays_qs = plays_qs.filter(played_at__gte=dt)
            if has_field(AlbumSale, "purchased_at"):
                sales_qs = sales_qs.filter(purchased_at__gte=dt)
            if rate_qs is not None and has_field(Rating, "rated_at"):
                rate_qs = rate_qs.filter(rated_at__gte=dt)
    if t:
        dt = parse_datetime(t)
        if dt and has_field(Playback, "played_at"):
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

    if (request.query_params.get("include_refunds") or "").lower() not in TRUTHY and has_field(AlbumSale, "refunded"):
        sales_qs = sales_qs.filter(refunded=False)

    # Aggregate by artist_id (guard against missing fields)
    agg_p = []
    if has_field(Playback, "artist_id"):
        agg_p = plays_qs.values("artist_id").annotate(plays_total=Count("id"))

    agg_s = []
    if has_field(AlbumSale, "artist_id"):
        agg_s = sales_qs.values("artist_id").annotate(sales_orders=Count("id"), sales_units=Sum("units"))

    agg_r = []
    if rate_qs is not None and has_field(Rating, "artist_id"):
        agg_r = rate_qs.values("artist_id").annotate(ratings_count=Count("id"), ratings_average=Avg("stars"))

    by_artist = {}
    for row in agg_p:
        aid = row["artist_id"]
        by_artist[aid] = {"artist_id": aid, "plays": row["plays_total"], "sales_orders": 0, "sales_units": 0, "ratings_count": 0, "ratings_average": None}

    for row in agg_s:
        aid = row["artist_id"]
        cur = by_artist.setdefault(aid, {"artist_id": aid, "plays": 0, "sales_orders": 0, "sales_units": 0, "ratings_count": 0, "ratings_average": None})
        cur["sales_orders"] = row.get("sales_orders") or 0
        cur["sales_units"] = row.get("sales_units") or 0

    for row in agg_r:
        aid = row["artist_id"]
        cur = by_artist.setdefault(aid, {"artist_id": aid, "plays": 0, "sales_orders": 0, "sales_units": 0, "ratings_count": 0, "ratings_average": None})
        cur["ratings_count"] = row.get("ratings_count") or 0
        cur["ratings_average"] = round(float(row.get("ratings_average")), 2) if row.get("ratings_average") is not None else None

    # Sorting and pagination
    sort = (request.query_params.get("sort") or "plays").lower()
    limit = int(request.query_params.get("limit") or 20)
    offset = int(request.query_params.get("offset") or 0)

    items = list(by_artist.values())
    if sort == "sales":
        items.sort(key=lambda x: x.get("sales_units", 0), reverse=True)
    elif sort == "ratings":
        items.sort(key=lambda x: (x.get("ratings_average") or 0), reverse=True)
    else:
        items.sort(key=lambda x: x.get("plays", 0), reverse=True)

    total = len(items)
    page = items[offset : offset + limit]

    # Optional enrichment from contenidos
    if request.query_params.get("enrich") and page:
        ids = ",".join([str(i.get("artist_id")) for i in page if i.get("artist_id")])
        if ids:
            try:
                artists_meta = _fetch_artists_meta_by_ids(ids)
                for it in page:
                    aid = it.get("artist_id")
                    if aid and str(aid) in artists_meta:
                        it["artist"] = artists_meta[str(aid)]
            except Exception:
                # non-fatal: leave items as-is
                pass

    return Response({"total": total, "limit": limit, "offset": offset, "items": page})

@api_view(["GET"])
@permission_classes([IsDiscografica])
def artists_ratings(request):
    """Return aggregated ratings per artist.

    Query params:
    - `limit` (int): number of artists to return (default 20)
    - `offset` (int): pagination offset (default 0)
    - `sort` (count|average) default 'count' (desc)
    - `from`, `to` filters applied to `rated_at`
    - `enrich` (1|true) if present will call contenidos to get artist metadata
    """
    Rating = get_rating_model()
    if Rating is None:
        return Response({"detail": "Rating model not available."}, status=400)

    qs = Rating.objects.all()

    f = request.query_params.get("from")
    t = request.query_params.get("to")
    if f:
        dt = parse_datetime(f)
        if dt and has_field(Rating, "rated_at"):
            qs = qs.filter(rated_at__gte=dt)
    if t:
        dt = parse_datetime(t)
        if dt and has_field(Rating, "rated_at"):
            qs = qs.filter(rated_at__lte=dt)

    if not has_field(Rating, "artist_id"):
        return Response({"detail": "Rating model does not have artist_id field."}, status=400)

    agg = qs.values("artist_id").annotate(count=Count("id"), average=Avg("stars"))

    items = []
    for row in agg:
        items.append({
            "artist_id": row["artist_id"],
            "ratings_count": row["count"],
            "ratings_average": round(float(row["average"]), 2) if row["average"] is not None else None,
        })

    sort = (request.query_params.get("sort") or "count").lower()
    if sort == "average":
        items.sort(key=lambda x: (x.get("ratings_average") or 0), reverse=True)
    else:
        items.sort(key=lambda x: x.get("ratings_count", 0), reverse=True)

    limit = int(request.query_params.get("limit") or 20)
    offset = int(request.query_params.get("offset") or 0)
    total = len(items)
    page = items[offset: offset + limit]

    if request.query_params.get("enrich") and page:
        ids = ",".join([str(i.get("artist_id")) for i in page if i.get("artist_id")])
        if ids:
            try:
                artists_meta = _fetch_artists_meta_by_ids(ids)
                for it in page:
                    aid = it.get("artist_id")
                    if aid and str(aid) in artists_meta:
                        it["artist"] = artists_meta[str(aid)]
            except Exception:
                # non-fatal
                pass

    return Response({"total": total, "limit": limit, "offset": offset, "items": page})


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
