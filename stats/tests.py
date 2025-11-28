from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse


class ArtistsRatingsTest(TestCase):
	def test_artists_ratings_aggregates(self):
		User = get_user_model()
		user = User.objects.create(username="tu_test_user", is_superuser=True)
		# create a rating linked to this user
		from .models import Rating

		Rating.objects.create(user=user, song_id="s1", artist_id="artist-test", stars=4)

		self.client.force_login(user)
		resp = self.client.get("/api/v1/stats/artists/ratings?limit=10&sort=count")
		self.assertEqual(resp.status_code, 200)
		data = resp.json()
		self.assertGreaterEqual(data.get("total", 0), 1)
		items = data.get("items", [])
		# find our artist
		found = [i for i in items if i.get("artist_id") == "artist-test"]
		self.assertTrue(found)
