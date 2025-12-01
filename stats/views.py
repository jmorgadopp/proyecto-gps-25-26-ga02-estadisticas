
"""
Copied views implementation into top-level `stats` package.

This file is self-contained and mirrors the implementation previously
living under `backend_estadisticas.stats.views`. Keeping a full copy here
avoids import-time circularities and makes `stats` the canonical app.
"""
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
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db import IntegrityError

from .serializers import RatingSerializer

from .permissions import IsDiscografica
import requests
from django.conf import settings


def normalize_song_id(song_id: str):
    if not song_id:
        return song_id
    content_api = getattr(settings, "CONTENT_API_BASE", "http://127.0.0.1:8001/api/v1")
    try:
        r = requests.get(f"{content_api}/tracks/{song_id}", timeout=2)
        if r.ok:
            data = r.json()
            tid = data.get("id") or data.get("track_id") or data.get("song_id") or data.get("uuid")
            if tid:
                return str(tid)
    except Exception:
        pass

    candidates = []
    qs = [("title", song_id), ("search", song_id), ("q", song_id)]
    for param, val in qs:
        try:
            r = requests.get(f"{content_api}/tracks", params={param: val}, timeout=3)
            if not r.ok:
                continue
            j = r.json()
            items = j if isinstance(j, list) else (j.get("items") or j.get("results") or [])
            if not items:
                continue
            for it in items:
                if not it:
                    continue
                key = it.get("id") or it.get("track_id") or it.get("song_id") or it.get("uuid")
                if key:
                    candidates.append(str(key))
        except Exception:
            continue
    if len(set(candidates)) == 1:
        return list(set(candidates))[0]
    return song_id


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


TRUTHY = {"1", "true", "yes", "y", "t"}
FALSY = {"0", "false", "no", "n", "f"}


def has_field(model, name: str) -> bool:
    return model is not None and any(f.name == name for f in model._meta.get_fields())


@api_view(["GET"])
@permission_classes([AllowAny])
def rating_by_song(request, song_id: str):
    Rating = get_rating_model()
    if Rating is None:
        return Response({"song_id": song_id, "count": 0, "average": None}, status=200)

    qs = Rating.objects.filter(song_id=song_id)
    count = qs.count()
    avg = qs.aggregate(avg=Avg("stars"))["avg"]
    return Response({"song_id": song_id, "count": count, "average": (round(float(avg), 2) if avg is not None else None)}, status=200)


@api_view(["GET"])
@permission_classes([AllowAny])
def song_aggregate(request, song_id: str):
    Rating = get_rating_model()
    if Rating is None:
        return Response({"song_id": song_id, "ratings_count": 0, "ratings_average": None}, status=200)

    try:
        qs = Rating.objects.filter(song_id=song_id)
        count = qs.count()
        avg = qs.aggregate(avg=Avg("stars"))["avg"]
        return Response({"song_id": song_id, "ratings_count": count, "ratings_average": (round(float(avg), 4) if avg is not None else None)}, status=200)
    except Exception as e:
        return Response({"song_id": song_id, "ratings_count": 0, "ratings_average": None, "error": str(e)}, status=500)


@api_view(["GET"])
@permission_classes([AllowAny])
def artist_aggregate(request, artist_id: str):
    Rating = get_rating_model()
    if Rating is None:
        return Response({"artist_id": artist_id, "ratings_count": 0, "ratings_average": None}, status=200)

    try:
        qs = Rating.objects.filter(artist_id=str(artist_id))
        count = qs.count()
        avg = qs.aggregate(avg=Avg("stars"))["avg"]
        if count:
            return Response({"artist_id": str(artist_id), "ratings_count": count, "ratings_average": (round(float(avg), 4) if avg is not None else None)}, status=200)

        content_api = getattr(settings, "CONTENT_API_BASE", "http://127.0.0.1:8001/api/v1")
        try:
            r = requests.get(f"{content_api}/artists/{artist_id}/tracks", timeout=5)
            if not r.ok:
                return Response({"artist_id": str(artist_id), "ratings_count": 0, "ratings_average": None}, status=200)
            tb = r.json()
            items = tb if isinstance(tb, list) else (tb.get("items") or tb.get("results") or [])
            tids = [str(tr.get("id") or tr.get("track_id") or tr.get("uuid") or tr.get("song_id")) for tr in items if (tr.get("id") or tr.get("track_id") or tr.get("uuid") or tr.get("song_id"))]
            if not tids:
                return Response({"artist_id": str(artist_id), "ratings_count": 0, "ratings_average": None}, status=200)

            qs2 = Rating.objects.filter(song_id__in=tids)
            count2 = qs2.count()
            avg2 = qs2.aggregate(avg=Avg("stars"))["avg"]
            return Response({"artist_id": str(artist_id), "ratings_count": count2, "ratings_average": (round(float(avg2), 4) if avg2 is not None else None)}, status=200)
        except Exception:
            return Response({"artist_id": str(artist_id), "ratings_count": 0, "ratings_average": None}, status=200)
    except Exception as e:
        return Response({"artist_id": str(artist_id), "ratings_count": 0, "ratings_average": None, "error": str(e)}, status=500)


def _fetch_artists_meta_by_ids(ids_csv: str):
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
                continue
    except Exception:
        return meta

    return meta


@api_view(["GET", "POST", "DELETE"])
@permission_classes([AllowAny])
def plays_by_song(request, song_id: str):
    Playback = get_playback_model()

    if request.method == "POST":
        label = request.data.get("label_id") or request.headers.get("X-Label-Id") or request.META.get("HTTP_X_LABEL_ID")

        if not label and has_field(Playback, "label_id"):
            try:
                content_api = getattr(settings, "CONTENT_API_BASE", "http://127.0.0.1:8001/api/v1")
                url = f"{content_api}/tracks/{song_id}"
                r = requests.get(url, timeout=2)
                if r.ok:
                    data = r.json()
                    artist = data.get("artist") or {}
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
        total = Playback.objects.filter(song_id=song_id).count()
        return Response({"song_id": song_id, "plays": total, "changed": +1}, status=201)

    if request.method == "DELETE":
        qs = Playback.objects.filter(song_id=song_id)
        if has_field(Playback, "played_at"):
            qs = qs.order_by("-played_at")
        else:
            qs = qs.order_by("-id")
        last = qs.first()
        if last:
            last.delete()
            total = Playback.objects.filter(song_id=song_id).count()
            return Response({"song_id": song_id, "plays": total, "changed": -1}, status=200)
        else:
            total = Playback.objects.filter(song_id=song_id).count()
            return Response({"song_id": song_id, "plays": total, "changed": 0}, status=200)

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
    if AlbumSale is None:
        return Response({"album_id": album_id, "sales_count": 0, "units_sold": 0, "revenue": 0, "last_purchase": None}, status=200)

    try:
        qs = AlbumSale.objects.filter(album_id=album_id)
        count = qs.count()
        units = qs.aggregate(total_units=Sum('units'))['total_units'] or 0
        revenue = qs.aggregate(total_amount=Sum('amount'))['total_amount'] or 0
        last = qs.order_by("-purchased_at").first()
        last_purchase = last.purchased_at.isoformat() if last and getattr(last, "purchased_at", None) else None
        return Response({
            "album_id": album_id,
            "sales_count": count,
            "units_sold": int(units),
            "revenue": float(revenue) if revenue is not None else 0,
            "last_purchase": last_purchase,
        }, status=200)
    except Exception as e:
        return Response({"album_id": album_id, "sales_count": 0, "units_sold": 0, "revenue": 0, "last_purchase": None, "error": str(e)}, status=500)


def _collect_artist_aggregates(limit: int = None, offset: int = 0, sort: str = "count"):
    Rating = get_rating_model()
    if Rating is None:
        return 0, []

    qs = Rating.objects.values("artist_id").annotate(ratings_count=Count("id"), ratings_average=Avg("stars"))

    if sort in ("count", "-count"):
        qs = qs.order_by("-ratings_count")
    elif sort in ("average", "-average"):
        qs = qs.order_by("-ratings_average")
    else:
        qs = qs.order_by("-ratings_count")

    total = qs.count()
    if offset:
        qs = qs[offset:]
    if limit:
        qs = qs[:limit]

    items = []
    ids = []
    for row in qs:
        aid = row.get("artist_id") or ""
        ids.append(str(aid))
        items.append({
            "artist_id": str(aid),
            "ratings_count": int(row.get("ratings_count") or 0),
            "ratings_average": (round(float(row.get("ratings_average")), 4) if row.get("ratings_average") is not None else None),
        })

    if ids:
        meta = _fetch_artists_meta_by_ids(",".join(ids))
        for it in items:
            a = meta.get(str(it["artist_id"]))
            if a and a.get("name"):
                it["name"] = a.get("name")

    return total, items


@api_view(["GET"])
@permission_classes([AllowAny])
def artists_ratings(request):
    try:
        limit = int(request.query_params.get("limit") or 0) or None
    except Exception:
        limit = None
    try:
        offset = int(request.query_params.get("offset") or 0) or 0
    except Exception:
        offset = 0
    sort = request.query_params.get("sort") or "count"

    total, items = _collect_artist_aggregates(limit=limit, offset=offset, sort=sort)
    return Response({"total": total, "items": items}, status=200)


@api_view(["GET"])
@permission_classes([AllowAny])
def artists_stats(request):
    return artists_ratings(request)


class SongRatingsListCreateView(generics.ListCreateAPIView):
    serializer_class = RatingSerializer

    permission_classes = [AllowAny]

    def get_queryset(self):
        Rating = get_rating_model()
        song_id = self.kwargs.get("song_id")
        if Rating is None:
            return Rating.objects.none() if Rating is not None else []
        return Rating.objects.filter(song_id=song_id).order_by("-rated_at")

    def perform_create(self, serializer):
        Rating = get_rating_model()
        if Rating is None:
            raise IntegrityError("Rating model not available")

        song_id = self.kwargs.get("song_id")
        canonical = normalize_song_id(song_id)
        User = get_user_model()
        req_user = getattr(self.request, "user", None)
        if req_user and getattr(req_user, "is_authenticated", False):
            user_obj = req_user
        else:
            user_obj, _ = User.objects.get_or_create(username="anonymous", defaults={"is_active": False})

        serializer.save(user=user_obj, song_id=str(canonical))


class RatingDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = RatingSerializer

    permission_classes = [AllowAny]

    def get_queryset(self):
        Rating = get_rating_model()
        if Rating is None:
            return []
        return Rating.objects.all()

    def get_object(self):
        return super().get_object()

    def perform_update(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        instance.delete()


@api_view(["GET"])
@permission_classes([AllowAny])
def global_stats(request):
    Rating = get_rating_model()
    Playback = get_playback_model()
    AlbumSale = get_album_sale_model()

    try:
        ratings_count = Rating.objects.count() if Rating is not None else 0
        ratings_avg = Rating.objects.aggregate(avg=Avg("stars"))["avg"] if Rating is not None else None
    except Exception:
        ratings_count = 0
        ratings_avg = None

    try:
        plays_count = Playback.objects.count() if Playback is not None else 0
    except Exception:
        plays_count = 0

    try:
        album_sales_count = AlbumSale.objects.count() if AlbumSale is not None else 0
    except Exception:
        album_sales_count = 0

    return Response({
        "ratings_count": ratings_count,
        "ratings_average": (round(float(ratings_avg), 4) if ratings_avg is not None else None),
        "plays_count": plays_count,
        "album_sales_count": album_sales_count,
    }, status=200)



@api_view(["GET"])
@permission_classes([AllowAny])
def artists_aggregate(request):
    """Return per-artist rating aggregates.

    This endpoint attempts to compute ratings_count and ratings_average per
    artist using DB-side aggregation when the `artist_id` field exists on the
    Rating model. For ratings that lack `artist_id`, it will attempt to resolve
    the track -> artist mapping by calling the contenidos service in bulk and
    include those ratings in the aggregation. The response shape is compatible
    with the frontend expectations: { total, items: [ { artist_id, ratings_count, ratings_average, artist? } ] }
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

    # First aggregate ratings that already have artist_id set
    items_map = {}
    if has_field(Rating, "artist_id"):
        agg_known = qs.exclude(artist_id__isnull=True).values("artist_id").annotate(count=Count("id"), average=Avg("stars"))
        for row in agg_known:
            aid = row.get("artist_id")
            if aid is None:
                continue
            # Keep a stable string key for lookups, but return a numeric id when possible
            key = str(aid)
            artist_id_value = aid
            try:
                if isinstance(aid, str) and aid.isdigit():
                    artist_id_value = int(aid)
            except Exception:
                artist_id_value = aid
            items_map[key] = {"artist_id": artist_id_value, "ratings_count": int(row.get("count") or 0), "ratings_average": round(float(row.get("average")), 2) if row.get("average") is not None else None}

    # Now handle ratings without artist_id by resolving their song -> artist mapping
    unknown_qs = qs.filter(artist_id__isnull=True).values("song_id").annotate(count=Count("id"), sum_stars=Sum("stars"))
    song_map = {}
    song_ids = [str(r.get("song_id")) for r in unknown_qs if r.get("song_id")]
    if song_ids:
        content_api = getattr(settings, "CONTENT_API_BASE", "http://127.0.0.1:8001/api/v1")
        try:
            # Bulk fetch tracks metadata; try `tracks?ids=...` then fall back to per-track
            ids_csv = ",".join(song_ids)
            r = requests.get(f"{content_api}/tracks?ids={ids_csv}", timeout=5)
            tracks = []
            if r.ok:
                try:
                    resp = r.json()
                except Exception:
                    resp = None
                if isinstance(resp, list):
                    tracks = resp
                elif isinstance(resp, dict):
                    tracks = resp.get("items") or resp.get("results") or []
            # If bulk fetch failed, try per-track (best-effort)
            if not tracks:
                tracks = []
                for sid in song_ids:
                    try:
                        r2 = requests.get(f"{content_api}/tracks/{sid}", timeout=3)
                        if r2.ok:
                            data = r2.json()
                            tracks.append(data)
                    except Exception:
                        continue

            for t in tracks:
                if not t:
                    continue
                sid = t.get("id") or t.get("song_id") or t.get("track_id") or t.get("uuid")
                artist = None
                if isinstance(t.get("artist"), dict):
                    artist = t["artist"].get("id") or t["artist"].get("artist_id")
                artist = artist or t.get("artist_id") or t.get("artistId")
                if sid:
                    song_map[str(sid)] = str(artist) if artist is not None else None
        except Exception:
            # Best-effort: if fetching fails, song_map stays empty and we won't attribute unknown ratings
            song_map = {}

    # If some song_ids were not resolved by id, attempt a best-effort title search
    # using the contenidos `/tracks/search?q=` endpoint. Only accept unique matches.
    unresolved = [str(r.get("song_id")) for r in unknown_qs if r.get("song_id") and str(r.get("song_id")) not in song_map]
    if unresolved:
        try:
            for sid in unresolved:
                # skip obviously numeric ids (already attempted) but keep titles and mixed strings
                if str(sid).isdigit():
                    continue
                try:
                    r2 = requests.get(f"{content_api}/tracks/search?q={requests.utils.requote_uri(str(sid))}", timeout=3)
                except Exception:
                    # fall back to simple encode
                    from urllib.parse import quote_plus
                    try:
                        r2 = requests.get(f"{content_api}/tracks/search?q={quote_plus(str(sid))}", timeout=3)
                    except Exception:
                        continue
                if not r2.ok:
                    continue
                try:
                    resp = r2.json()
                except Exception:
                    resp = None
                items = []
                if isinstance(resp, dict):
                    items = resp.get('items') or resp.get('results') or []
                elif isinstance(resp, list):
                    items = resp
                # Only accept unique match
                if len(items) == 1:
                    t = items[0]
                    artist = None
                    if isinstance(t.get('artist'), dict):
                        artist = t['artist'].get('id') or t['artist'].get('artist_id')
                    artist = artist or t.get('artist_id') or t.get('artistId')
                    if artist is not None:
                        song_map[str(sid)] = str(artist)
        except Exception:
            # non-fatal: proceed with whatever mapping we have
            pass

    for row in unknown_qs:
        sid = row.get("song_id")
        if not sid:
            continue
        aid = song_map.get(str(sid))
        if not aid:
            # can't attribute this song to any artist
            continue
        # normalize artist id value when possible
        artist_key = str(aid)
        artist_id_value = aid
        try:
            if isinstance(aid, str) and aid.isdigit():
                artist_id_value = int(aid)
        except Exception:
            artist_id_value = aid
        cur = items_map.setdefault(artist_key, {"artist_id": artist_id_value, "ratings_count": 0, "ratings_average": None})
        # merge counts and averages by converting to sums
        existing_count = cur.get("ratings_count") or 0
        existing_avg = cur.get("ratings_average")
        existing_sum = (existing_avg * existing_count) if (existing_avg is not None and existing_count) else 0
        add_count = int(row.get("count") or 0)
        add_sum = float(row.get("sum_stars") or 0)
        total_count = existing_count + add_count
        total_sum = existing_sum + add_sum
        cur["ratings_count"] = int(total_count)
        cur["ratings_average"] = round(float(total_sum / total_count), 2) if total_count > 0 else None

    items = list(items_map.values())
    # Sorting
    sort = (request.query_params.get("sort") or "average").lower()
    if sort == "count":
        items.sort(key=lambda x: x.get("ratings_count", 0), reverse=True)
    else:
        items.sort(key=lambda x: (x.get("ratings_average") or 0), reverse=True)

    limit = int(request.query_params.get("limit") or 100)
    offset = int(request.query_params.get("offset") or 0)
    total = len(items)
    page = items[offset: offset + limit]

    # Optional enrichment
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

    # We'll compute artist aggregates including ratings that lack artist_id by
    # resolving song_id -> artist via the contenidos service (best-effort).
    items_map = {}

    # First aggregate ratings that already have artist_id set (DB-side)
    if has_field(Rating, "artist_id"):
        agg_known = qs.exclude(artist_id__isnull=True).values("artist_id").annotate(count=Count("id"), average=Avg("stars"))
        for row in agg_known:
            aid = row.get("artist_id")
            if aid is None:
                continue
            items_map[str(aid)] = {
                "artist_id": (int(aid) if isinstance(aid, str) and aid.isdigit() else aid),
                "ratings_count": int(row.get("count") or 0),
                "ratings_average": round(float(row.get("average")), 2) if row.get("average") is not None else None,
            }

    # Now handle ratings without artist_id by mapping song_id -> artist
    unknown_qs = qs.filter(artist_id__isnull=True).values("song_id").annotate(count=Count("id"), sum_stars=Sum("stars"))
    song_ids = [str(r.get("song_id")) for r in unknown_qs if r.get("song_id")]
    song_map = {}
    if song_ids:
        content_api = getattr(settings, "CONTENT_API_BASE", "http://127.0.0.1:8001/api/v1")
        try:
            ids_csv = ",".join(song_ids)
            r = requests.get(f"{content_api}/tracks?ids={ids_csv}", timeout=5)
            tracks = []
            if r.ok:
                try:
                    resp = r.json()
                except Exception:
                    resp = None
                if isinstance(resp, list):
                    tracks = resp
                elif isinstance(resp, dict):
                    tracks = resp.get("items") or resp.get("results") or []
            if not tracks:
                tracks = []
                for sid in song_ids:
                    try:
                        r2 = requests.get(f"{content_api}/tracks/{sid}", timeout=3)
                        if r2.ok:
                            data = r2.json()
                            tracks.append(data)
                    except Exception:
                        continue

            for t in tracks:
                if not t:
                    continue
                sid = t.get("id") or t.get("song_id") or t.get("track_id") or t.get("uuid")
                artist = None
                if isinstance(t.get("artist"), dict):
                    artist = t["artist"].get("id") or t["artist"].get("artist_id")
                artist = artist or t.get("artist_id") or t.get("artistId")
                if sid:
                    song_map[str(sid)] = str(artist) if artist is not None else None
        except Exception:
            song_map = {}

    # Merge unknown-song aggregates into artist buckets using sums
    for row in unknown_qs:
        sid = row.get("song_id")
        if not sid:
            continue
        aid = song_map.get(str(sid))
        if not aid:
            continue
        key = str(aid)
        cur = items_map.setdefault(key, {"artist_id": (int(aid) if isinstance(aid, str) and aid.isdigit() else aid), "ratings_count": 0, "ratings_average": None})
        existing_count = cur.get("ratings_count") or 0
        existing_avg = cur.get("ratings_average")
        existing_sum = (existing_avg * existing_count) if (existing_avg is not None and existing_count) else 0
        add_count = int(row.get("count") or 0)
        add_sum = float(row.get("sum_stars") or 0)
        total_count = existing_count + add_count
        total_sum = existing_sum + add_sum
        cur["ratings_count"] = int(total_count)
        cur["ratings_average"] = round(float(total_sum / total_count), 2) if total_count > 0 else None

    items = list(items_map.values())

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
                pass

    return Response({"total": total, "limit": limit, "offset": offset, "items": page})



