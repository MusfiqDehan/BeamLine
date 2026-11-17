import time
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from common.tenancy import Organization, OrganizationMember, PlatformSettings
from crm.services.auth_service import GoogleOAuthService, JWTService

User = get_user_model()


@pytest.mark.django_db
def test_jwt_generation_and_decode():
    kevin_org = Organization.objects.get(slug="kevin")
    user = User.objects.get(username="kevin")

    tokens = JWTService.generate_token_pair(user, kevin_org, role="Owner")
    assert "access_token" in tokens
    assert "refresh_token" in tokens

    payload = JWTService.decode(tokens["access_token"])
    assert payload["user_id"] == str(user.id)
    assert payload["organization_slug"] == "kevin"
    assert payload["role"] == "Owner"
    assert payload["type"] == "access"


@pytest.mark.django_db
def test_login_api_view_success_and_failure():
    client = Client()
    # Test valid login with Kevin
    res_ok = client.post(
        "/api/v1/auth/login/",
        {"username_or_email": "kevin", "password": "kevinpass2026"},
        content_type="application/json",
        HTTP_X_TENANT_SLUG="kevin",
    )
    assert res_ok.status_code == 200
    data = res_ok.json()["data"]
    assert "tokens" in data
    assert data["user"]["username"] == "kevin"
    assert data["role"] == "Owner"

    # Test invalid login
    res_bad = client.post(
        "/api/v1/auth/login/",
        {"username_or_email": "kevin", "password": "wrongpassword"},
        content_type="application/json",
        HTTP_X_TENANT_SLUG="kevin",
    )
    assert res_bad.status_code == 401


@pytest.mark.django_db
def test_two_tier_google_oauth_resolution():
    from integrations.services.resolver import IntegrationResolver

    client = Client()
    p_cfg = IntegrationResolver.ensure_platform_config("google_oauth")
    p_cfg.is_enabled_globally = True
    p_cfg.allow_platform_credentials_fallback = True
    p_cfg.set_credentials(
        {
            "client_id": "platform-global-id.apps.googleusercontent.com",
            "client_secret": "platform-secret",
        },
        secret_keys={"client_secret"},
    )
    p_cfg.save()

    kevin_org = Organization.objects.get(slug="kevin")
    t_cfg = IntegrationResolver.get_or_create_tenant_config("google_oauth", kevin_org)
    t_cfg.is_enabled = False
    t_cfg.save()

    # 1. Tier 1 fallback: when client custom oauth is disabled, use platform oauth
    res_plat = client.get("/api/v1/auth/oauth-config/", HTTP_X_TENANT_SLUG="kevin")
    assert res_plat.status_code == 200
    oauth_data = res_plat.json()["data"]["google_oauth"]
    assert oauth_data["source"] == "platform"
    assert oauth_data["client_id"] == "platform-global-id.apps.googleusercontent.com"

    # 2. Tier 2 override: when client configures and enables custom Google OAuth
    t_cfg.is_enabled = True
    t_cfg.use_custom_credentials = True
    t_cfg.set_credentials(
        {
            "client_id": "kevin-custom-id.apps.googleusercontent.com",
            "client_secret": "kevin-custom-secret",
        },
        secret_keys={"client_secret"},
    )
    t_cfg.save()

    res_client = client.get("/api/v1/auth/oauth-config/", HTTP_X_TENANT_SLUG="kevin")
    assert res_client.status_code == 200
    oauth_client_data = res_client.json()["data"]["google_oauth"]
    assert oauth_client_data["source"] == "client"
    assert oauth_client_data["client_id"] == "kevin-custom-id.apps.googleusercontent.com"
    assert oauth_client_data["brand_name"] == "Kevin's Custom Homes"


@pytest.mark.django_db
def test_google_oauth_login_with_mock_token():
    client = Client()
    kevin_org = Organization.objects.get(slug="kevin")

    # Use test fixture token format: test_google_token_<email>
    res = client.post(
        "/api/v1/auth/google/",
        {"id_token": "test_google_token_newpm@kevinbuild.com"},
        content_type="application/json",
        HTTP_X_TENANT_SLUG="kevin",
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["user"]["email"] == "newpm@kevinbuild.com"
    assert "tokens" in data


@pytest.mark.django_db
def test_register_api_view_success_and_workspace_creation():
    client = Client()
    payload = {
        "email": "jane@apexbuilds.com",
        "password": "apexpassword2026",
        "full_name": "Jane Builder",
        "organization_name": "Apex Custom Builds",
        "organization_slug": "apex",
    }
    res = client.post(
        "/api/v1/auth/register/",
        payload,
        content_type="application/json",
    )
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["user"]["email"] == "jane@apexbuilds.com"
    assert data["organization"]["slug"] == "apex"
    assert data["organization"]["name"] == "Apex Custom Builds"
    assert data["role"] == "Owner"
    assert "tokens" in data
    assert Organization.objects.filter(slug="apex").exists()
    assert User.objects.filter(email="jane@apexbuilds.com").exists()


@pytest.mark.django_db
def test_login_succeeds_even_with_expired_bearer_token_in_header():
    client = Client()
    kevin_user = User.objects.get(username="kevin")
    kevin_org = Organization.objects.get(slug="kevin")

    expired_access = JWTService.encode(
        {
            "type": "access",
            "user_id": str(kevin_user.id),
            "email": kevin_user.email,
            "username": kevin_user.username,
            "is_superuser": False,
            "organization_id": str(kevin_org.id),
            "organization_slug": kevin_org.slug,
            "role": "Owner",
            "iat": int(time.time()) - 7200,
            "exp": int(time.time()) - 3600,
        }
    )

    # Protected endpoint rejects expired token with 401
    protected_res = client.get(
        "/api/v1/tenant/settings/",
        HTTP_AUTHORIZATION=f"Bearer {expired_access}",
        HTTP_X_TENANT_SLUG="kevin",
    )
    assert protected_res.status_code == 401

    # Seeded credential logins MUST succeed even if an expired token is sent
    for username, password in [("kevin", "kevinpass2026"), ("admin", "adminpass2026")]:
        res = client.post(
            "/api/v1/auth/login/",
            {"username_or_email": username, "password": password},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {expired_access}",
            HTTP_X_TENANT_SLUG="kevin",
        )
        assert res.status_code == 200
        payload = res.json()["data"]
        assert payload["user"]["username"] == username
        assert payload["tokens"]["access_token"]
        assert payload["tokens"]["refresh_token"]


@pytest.mark.django_db
def test_dynamic_refresh_token_renewal_and_validation():
    client = Client()
    kevin_user = User.objects.get(username="kevin")
    kevin_org = Organization.objects.get(slug="kevin")

    login_res = client.post(
        "/api/v1/auth/login/",
        {"username_or_email": "kevin", "password": "kevinpass2026", "remember_me": True},
        content_type="application/json",
        HTTP_X_TENANT_SLUG="kevin",
    )
    assert login_res.status_code == 200
    tokens = login_res.json()["data"]["tokens"]

    # Refresh succeeds and mints a fresh valid access & refresh token pair
    refresh_res = client.post(
        "/api/v1/auth/refresh/",
        {"refresh_token": tokens["refresh_token"]},
        content_type="application/json",
        HTTP_X_TENANT_SLUG="kevin",
    )
    assert refresh_res.status_code == 200
    refreshed_data = refresh_res.json()["data"]
    assert refreshed_data["user"]["username"] == "kevin"
    assert refreshed_data["role"] == "Owner"
    assert refreshed_data["tokens"]["remember_me"] is True
    new_access = refreshed_data["tokens"]["access_token"]

    # New access token authenticates /auth/me/
    me_res = client.get(
        "/api/v1/auth/me/",
        HTTP_AUTHORIZATION=f"Bearer {new_access}",
        HTTP_X_TENANT_SLUG="kevin",
    )
    assert me_res.status_code == 200
    assert me_res.json()["data"]["is_authenticated"] is True
    assert me_res.json()["data"]["user"]["username"] == "kevin"

    # Using an access token as a refresh token fails with 401
    bad_type_res = client.post(
        "/api/v1/auth/refresh/",
        {"refresh_token": new_access},
        content_type="application/json",
    )
    assert bad_type_res.status_code == 401

    # Using an expired refresh token fails with 401
    expired_refresh = JWTService.encode(
        {
            "type": "refresh",
            "user_id": str(kevin_user.id),
            "organization_id": str(kevin_org.id),
            "iat": int(time.time()) - 7200,
            "exp": int(time.time()) - 60,
        }
    )
    expired_res = client.post(
        "/api/v1/auth/refresh/",
        {"refresh_token": expired_refresh},
        content_type="application/json",
    )
    assert expired_res.status_code == 401


@pytest.mark.django_db
def test_platform_admin_remember_me_feature_and_time_limit_governance():
    client = Client()
    admin_user = User.objects.get(username="admin")
    admin_tokens = JWTService.generate_token_pair(admin_user, role="Superadmin")
    admin_auth = f"Bearer {admin_tokens['access_token']}"

    # 1. Platform Admin configures Remember Me enabled with 14-day limit & 60m access token
    patch_res = client.patch(
        "/api/v1/superadmin/platform-settings/",
        {
            "remember_me_enabled": True,
            "remember_me_duration_days": 14,
            "access_token_lifetime_minutes": 60,
        },
        content_type="application/json",
        HTTP_AUTHORIZATION=admin_auth,
    )
    assert patch_res.status_code == 200
    plat_data = patch_res.json()["data"]
    assert plat_data["remember_me_enabled"] is True
    assert plat_data["remember_me_duration_days"] == 14
    assert plat_data["access_token_lifetime_minutes"] == 60

    # 2. Public oauth-config reflects admin Remember Me settings
    cfg_res = client.get("/api/v1/auth/oauth-config/", HTTP_X_TENANT_SLUG="kevin")
    assert cfg_res.status_code == 200
    rm_cfg = cfg_res.json()["data"]["remember_me"]
    assert rm_cfg["enabled"] is True
    assert rm_cfg["platform_enabled"] is True
    assert rm_cfg["tenant_enabled"] is True
    assert rm_cfg["duration_days"] == 14
    assert rm_cfg["access_token_lifetime_minutes"] == 60

    # 3. Login with remember_me=True issues 14-day refresh token & 60m access token
    login_res = client.post(
        "/api/v1/auth/login/",
        {"username_or_email": "kevin", "password": "kevinpass2026", "remember_me": True},
        content_type="application/json",
        HTTP_X_TENANT_SLUG="kevin",
    )
    assert login_res.status_code == 200
    tokens = login_res.json()["data"]["tokens"]
    assert tokens["remember_me"] is True
    assert tokens["remember_me_duration_days"] == 14
    assert tokens["expires_in"] == 60 * 60
    assert tokens["refresh_expires_in"] == 14 * 86400

    # 4. Refreshing preserves 14-day Remember Me policy
    refresh_res = client.post(
        "/api/v1/auth/refresh/",
        {"refresh_token": tokens["refresh_token"]},
        content_type="application/json",
        HTTP_X_TENANT_SLUG="kevin",
    )
    assert refresh_res.status_code == 200
    refreshed_tokens = refresh_res.json()["data"]["tokens"]
    assert refreshed_tokens["remember_me"] is True
    assert refreshed_tokens["remember_me_duration_days"] == 14
    assert refreshed_tokens["refresh_expires_in"] == 14 * 86400

    # 5. Platform Admin disables Remember Me globally -> login enforces remember_me=False
    disable_res = client.patch(
        "/api/v1/superadmin/platform-settings/",
        {"remember_me_enabled": False},
        content_type="application/json",
        HTTP_AUTHORIZATION=admin_auth,
    )
    assert disable_res.status_code == 200

    cfg_disabled = client.get("/api/v1/auth/oauth-config/", HTTP_X_TENANT_SLUG="kevin")
    assert cfg_disabled.json()["data"]["remember_me"]["enabled"] is False
    assert cfg_disabled.json()["data"]["remember_me"]["platform_enabled"] is False

    login_disabled = client.post(
        "/api/v1/auth/login/",
        {"username_or_email": "kevin", "password": "kevinpass2026", "remember_me": True},
        content_type="application/json",
        HTTP_X_TENANT_SLUG="kevin",
    )
    assert login_disabled.status_code == 200
    assert login_disabled.json()["data"]["tokens"]["remember_me"] is False
    assert login_disabled.json()["data"]["tokens"]["remember_me_duration_days"] == 0

    # 6. Platform Admin re-enables globally, but disables sub_auth_remember_me for Kevin tenant
    client.patch(
        "/api/v1/superadmin/platform-settings/",
        {"remember_me_enabled": True},
        content_type="application/json",
        HTTP_AUTHORIZATION=admin_auth,
    )
    kevin_org = Organization.objects.get(slug="kevin")
    feat_res = client.patch(
        f"/api/v1/superadmin/organizations/{kevin_org.id}/",
        {"feature_flags": {"sub_auth_remember_me": False}},
        content_type="application/json",
        HTTP_AUTHORIZATION=admin_auth,
    )
    assert feat_res.status_code == 200

    cfg_tenant_disabled = client.get("/api/v1/auth/oauth-config/", HTTP_X_TENANT_SLUG="kevin")
    assert cfg_tenant_disabled.json()["data"]["remember_me"]["enabled"] is False
    assert cfg_tenant_disabled.json()["data"]["remember_me"]["tenant_enabled"] is False

    login_tenant_disabled = client.post(
        "/api/v1/auth/login/",
        {"username_or_email": "kevin", "password": "kevinpass2026", "remember_me": True},
        content_type="application/json",
        HTTP_X_TENANT_SLUG="kevin",
    )
    assert login_tenant_disabled.status_code == 200
    assert login_tenant_disabled.json()["data"]["tokens"]["remember_me"] is False
