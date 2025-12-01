from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.apps import apps

# Use apps.get_model to avoid importing models directly (keeps migration
# compatibility during the refactor).
User = get_user_model()


class RatingSerializer(serializers.ModelSerializer):
	user_id = serializers.IntegerField(source='user.id', read_only=True)
	username = serializers.CharField(source='user.username', read_only=True)

	class Meta:
		model = apps.get_model('stats', 'Rating')
		fields = [
			'id', 'user_id', 'username', 'song_id', 'artist_id', 'stars', 'comment', 'rated_at'
		]
		read_only_fields = ['id', 'user_id', 'username', 'rated_at', 'song_id']
