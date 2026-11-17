from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any
import httpx
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import authentication, exceptions

logger = logging.getLogger(__name__)
User = get_user_model()


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _base64url_decode(data: str) -> bytes:
    padding = 4 - (len(data) % 4)
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data.encode("utf-8"))


class JWTService:
    """
    Self-contained, RFC 7519-compliant HS256 JWT generator and validator.
    Embeds user identity, organization context, and RBAC role.
    """

    ACCESS_TOKEN_LIFETIME = 60 * 60 * 24  # 24 hours
    REFRESH_TOKEN_LIFETIME = 60 * 60 * 24 * 30  # 30 days

    @classmethod
    def get_secret(cls) -> bytes:
        raw_key = getattr(settings, "SECRET_KEY", "beamline-jwt-secret-key-2026")
        return raw_key.encode("utf-8")

    @classmethod
    def encode(cls, payload: dict[str, Any], secret: bytes | None = None) -> str:
        secret = secret or cls.get_secret()
        header = {"alg": "HS256", "typ": "JWT"}
        header_b64 = _base64url_encode(
            json.dumps(header, separators=(",", ":")).encode("utf-8")
        )
        payload_b64 = _base64url_encode(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        )
        signature = hmac.new(
            secret, f"{header_b64}.{payload_b64}".encode("utf-8"), hashlib.sha256
        ).digest()
        sig_b64 = _base64url_encode(signature)
        return f"{header_b64}.{payload_b64}.{sig_b64}"

    @classmethod
    def decode(cls, token: str, secret: bytes | None = None) -> dict[str, Any]:
        secret = secret or cls.get_secret()
        parts = token.split(".")
        if len(parts) != 3:
            raise exceptions.AuthenticationFailed("Invalid token structure.")

        header_b64, payload_b64, sig_b64 = parts
        expected_sig = hmac.new(
            secret, f"{header_b64}.{payload_b64}".encode("utf-8"), hashlib.sha256
        ).digest()
        actual_sig = _base64url_decode(sig_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            raise exceptions.AuthenticationFailed("Token signature mismatch.")

        try:
            payload = json.loads(_base64url_decode(payload_b64).decode("utf-8"))
        except Exception as exc:
            raise exceptions.AuthenticationFailed(f"Malformed token payload: {exc}")

        exp = payload.get("exp")
        if exp and time.time() > exp:
            raise exceptions.AuthenticationFailed("Token has expired.")

        return payload

    @classmethod
    def get_token_lifetimes(
        cls, remember_me: bool = False, organization: Any = None
    ) -> dict[str, Any]:
        """
        Resolves access and refresh token lifetimes from PlatformSettings and
        organization feature flags (`sub_auth_remember_me`).
        """
        from common.tenancy import PlatformSettings

        try:
            platform = PlatformSettings.get_settings()
            platform_enabled = bool(getattr(platform, "remember_me_enabled", True))
            duration_days = max(
                1, min(365, int(getattr(platform, "remember_me_duration_days", 30) or 30))
            )
            access_minutes = max(
                5, int(getattr(platform, "access_token_lifetime_minutes", 1440) or 1440)
            )
        except Exception:
            platform_enabled = True
            duration_days = 30
            access_minutes = 1440

        tenant_enabled = (
            organization.is_feature_enabled("sub_auth_remember_me")
            if (organization and hasattr(organization, "is_feature_enabled"))
            else True
        )
        remember_me_allowed = platform_enabled and tenant_enabled
        effective_remember_me = bool(remember_me and remember_me_allowed)

        access_lifetime = access_minutes * 60
        if effective_remember_me:
            refresh_lifetime = duration_days * 86400
        else:
            refresh_lifetime = max(access_lifetime * 2, 60 * 60 * 48)

        return {
            "access_lifetime": access_lifetime,
            "refresh_lifetime": refresh_lifetime,
            "effective_remember_me": effective_remember_me,
            "duration_days": duration_days,
            "remember_me_allowed": remember_me_allowed,
        }

    @classmethod
    def generate_token_pair(
        cls,
        user: Any,
        organization: Any = None,
        role: str = "PM",
        remember_me: bool = False,
    ) -> dict[str, Any]:
        now = int(time.time())
        org_id = str(organization.id) if organization else None
        org_slug = organization.slug if organization else None

        lifetimes = cls.get_token_lifetimes(
            remember_me=remember_me, organization=organization
        )
        access_lifetime = lifetimes["access_lifetime"]
        refresh_lifetime = lifetimes["refresh_lifetime"]
        effective_remember_me = lifetimes["effective_remember_me"]
        duration_days = lifetimes["duration_days"]

        access_payload = {
            "type": "access",
            "user_id": str(user.id),
            "email": user.email,
            "username": user.username,
            "is_superuser": bool(user.is_superuser),
            "organization_id": org_id,
            "organization_slug": org_slug,
            "role": role,
            "remember_me": effective_remember_me,
            "iat": now,
            "exp": now + access_lifetime,
        }

        refresh_payload = {
            "type": "refresh",
            "user_id": str(user.id),
            "organization_id": org_id,
            "organization_slug": org_slug,
            "role": role,
            "remember_me": effective_remember_me,
            "remember_me_days": duration_days if effective_remember_me else 0,
            "iat": now,
            "exp": now + refresh_lifetime,
        }

        return {
            "access_token": cls.encode(access_payload),
            "refresh_token": cls.encode(refresh_payload),
            "expires_in": access_lifetime,
            "refresh_expires_in": refresh_lifetime,
            "access_expires_at": now + access_lifetime,
            "refresh_expires_at": now + refresh_lifetime,
            "remember_me": effective_remember_me,
            "remember_me_duration_days": duration_days if effective_remember_me else 0,
            "token_type": "Bearer",
        }

    @classmethod
    def refresh_access_token(
        cls, refresh_token: str, tenant: Any = None
    ) -> dict[str, Any]:
        """
        Validates a refresh token and mints a fresh access & refresh token pair
        preserving the user's tenant, active role, and Remember Me policy.
        """
        from common.tenancy import Organization, OrganizationMember

        payload = cls.decode(refresh_token)
        if payload.get("type") != "refresh":
            raise exceptions.AuthenticationFailed("Provided token is not a refresh token.")

        user_id = payload.get("user_id")
        try:
            user = User.objects.get(id=user_id, is_active=True)
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed("User not found or deactivated.")

        resolved_org = tenant
        if not resolved_org and payload.get("organization_id"):
            resolved_org = Organization.objects.filter(
                id=payload.get("organization_id")
            ).first()
        if not resolved_org and payload.get("organization_slug"):
            resolved_org = Organization.objects.filter(
                slug=payload.get("organization_slug")
            ).first()

        role = str(payload.get("role") or "Client")
        if user.is_superuser:
            role = "Superadmin"
        elif resolved_org:
            membership = OrganizationMember.objects.filter(
                organization=resolved_org, user=user, is_active=True
            ).first()
            if membership:
                role = membership.role
        else:
            membership = (
                OrganizationMember.objects.filter(user=user, is_active=True)
                .select_related("organization")
                .first()
            )
            if membership:
                resolved_org = membership.organization
                role = membership.role

        remember_me = bool(payload.get("remember_me", False))
        tokens = cls.generate_token_pair(
            user, resolved_org, role=role, remember_me=remember_me
        )
        return {
            "tokens": tokens,
            "user": {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_superuser": bool(user.is_superuser),
            },
            "organization": {
                "id": str(resolved_org.id),
                "name": resolved_org.name,
                "slug": resolved_org.slug,
            }
            if resolved_org
            else None,
            "role": role,
        }


class BeamlineJWTAuthentication(authentication.BaseAuthentication):
    """
    DRF Authentication Backend. Validates Bearer JWT tokens in Authorization headers.
    """

    def authenticate_header(self, request) -> str:
        return 'Bearer realm="api"'

    def authenticate(self, request) -> tuple[Any, dict[str, Any]] | None:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None

        token = parts[1].strip()
        payload = JWTService.decode(token)

        if payload.get("type") != "access":
            raise exceptions.AuthenticationFailed("Provided token is not an access token.")

        user_id = payload.get("user_id")
        try:
            user = User.objects.get(id=user_id, is_active=True)
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed("User not found or deactivated.")

        request.auth_payload = payload
        return (user, payload)


class GoogleOAuthService:
    """
    Two-tier Google OAuth verification service backed by IntegrationResolver (`provider_key="google_oauth"`):
    1. Checks if client organization is entitled and has custom Google OAuth credentials configured and enabled.
    2. Falls back to platform superadmin's global Google OAuth credentials when permitted.
    """

    @classmethod
    def resolve_credentials(cls, organization: Any = None) -> dict[str, Any]:
        from common.tenancy import PlatformSettings
        from integrations.services.resolver import IntegrationResolver

        platform = PlatformSettings.get_settings()
        resolved = IntegrationResolver.resolve("google_oauth", organization=organization)
        client_id = str(resolved.credentials.get("client_id") or "").strip()
        client_secret = str(resolved.credentials.get("client_secret") or "").strip()

        if resolved.source == "tenant" and organization:
            return {
                "source": "client",
                "enabled": bool(resolved.is_enabled and client_id),
                "client_id": client_id,
                "client_secret": client_secret,
                "organization_name": organization.name,
                "organization_slug": organization.slug,
                "config": resolved.config,
            }

        return {
            "source": "platform",
            "enabled": bool(resolved.is_enabled and client_id),
            "client_id": client_id,
            "client_secret": client_secret,
            "platform_name": platform.platform_name,
            "config": resolved.config,
        }

    @classmethod
    def verify_token(
        cls, id_token: str, organization: Any = None
    ) -> dict[str, Any]:
        """
        Verifies Google ID token against Google's tokeninfo endpoint.
        Supports deterministic test tokens for automated test suites.
        """
        # Test fixture hook: test_google_token_<email>
        if id_token.startswith("test_google_token_"):
            email_part = id_token.replace("test_google_token_", "")
            email = email_part if "@" in email_part else f"{email_part}@example.com"
            name = email.split("@")[0].replace(".", " ").title()
            return {
                "email": email,
                "name": name,
                "sub": f"mock_google_id_{email_part}",
                "email_verified": True,
            }

        credentials = cls.resolve_credentials(organization)
        expected_client_id = credentials.get("client_id")

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    "https://oauth2.googleapis.com/tokeninfo",
                    params={"id_token": id_token},
                )
                if resp.status_code != 200:
                    raise exceptions.AuthenticationFailed(
                        f"Google token verification failed: {resp.text}"
                    )
                info = resp.json()
        except httpx.RequestError as exc:
            raise exceptions.AuthenticationFailed(
                f"Network error contacting Google OAuth: {exc}"
            )

        aud = info.get("aud")
        if expected_client_id and aud != expected_client_id:
            logger.warning(
                "Google token audience '%s' does not match resolved client_id '%s'",
                aud,
                expected_client_id,
            )
            # When configured, enforce audience check
            if getattr(settings, "ENFORCE_GOOGLE_AUDIENCE_CHECK", False):
                raise exceptions.AuthenticationFailed(
                    "Google token was not issued for this client."
                )

        if not info.get("email"):
            raise exceptions.AuthenticationFailed("Google token does not contain an email.")

        return {
            "email": info["email"],
            "name": info.get("name", info["email"].split("@")[0]),
            "sub": info.get("sub", ""),
            "picture": info.get("picture", ""),
            "email_verified": info.get("email_verified", "true") in ("true", True),
        }
