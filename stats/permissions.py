"""Shim for permissions — re-export from reorganized backend."""
from django.conf import settings
from rest_framework.permissions import BasePermission

def _has_label_role(user) -> bool:
	if not user or not getattr(user, "is_authenticated", False):
		return False
	if getattr(user, "is_superuser", False):
		return True
	# Por grupo
	try:
		names = {g.name.lower() for g in user.groups.all()}
		if "discografica" in names or "discográfica" in names:
			return True
	except Exception:
		pass
	# Por atributo (posible perfil/propiedad custom)
	role = getattr(user, "role", None) or getattr(getattr(user, "profile", None), "role", None)
	return (role or "").lower() in {"discografica", "discográfica"}

class IsDiscografica(BasePermission):
	message = "Solo usuarios con rol 'discográfica' pueden acceder."

	def has_permission(self, request, view):
		# 1) Si DRF pobló request.user (Session/JWT)
		if _has_label_role(getattr(request, "user", None)):
			return True

		# 2) Modo DEV: header para pruebas manuales (no usar en prod)
		hdr = request.headers.get("X-User-Role") or request.META.get("HTTP_X_USER_ROLE")
		if getattr(settings, "DEBUG", False) and hdr and hdr.lower() in {"discografica", "discográfica"}:
			return True

		# 3) Si hay SimpleJWT configurado, intentamos autenticar
		try:
			from rest_framework_simplejwt.authentication import JWTAuthentication
			auth = JWTAuthentication().authenticate(request)
			if auth:
				user, token = auth
				if _has_label_role(user):
					return True
				role = token.payload.get("role") or token.payload.get("roles")
				if isinstance(role, str) and role.lower() in {"discografica", "discográfica"}:
					return True
				if isinstance(role, (list, tuple, set)) and {"discografica", "discográfica"} & {str(r).lower() for r in role}:
					return True
		except Exception:
			pass

		return False
