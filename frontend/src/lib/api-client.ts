import type { ApiEnvelope, AuthTokens, CursorPaginatedData } from "./types";

const ACCESS_TOKEN_KEY = "beamline_access_token";
const REFRESH_TOKEN_KEY = "beamline_refresh_token";
const AUTH_META_KEY = "beamline_auth_meta";
const REMEMBERED_CREDS_KEY = "beamline_remembered_credentials";
const TENANT_SLUG_KEY = "beamline_tenant_slug";

const PUBLIC_AUTH_PATHS = new Set([
  "/auth/login",
  "/auth/register",
  "/auth/google",
  "/auth/refresh",
  "/auth/oauth-config",
  "/invitations/accept",
]);

export interface RememberedCredentials {
  loginId: string;
  password?: string;
  durationDays: number;
  expiresAt: number;
}

interface StoredAuthMeta {
  rememberMe: boolean;
  durationDays: number;
  refreshExpiresAt: number;
  updatedAt: number;
}

function decodeBase64Url(segment: string): string {
  const base64 = segment.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
  if (typeof atob === "function") {
    return atob(padded);
  }
  return Buffer.from(padded, "base64").toString("utf-8");
}

export function isJwtExpired(token: string, bufferSeconds = 30): boolean {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return true;
    const payload = JSON.parse(decodeBase64Url(parts[1])) as { exp?: number };
    if (typeof payload.exp !== "number") return false;
    return Date.now() / 1000 + bufferSeconds >= payload.exp;
  } catch {
    return true;
  }
}

function isPublicAuthEndpoint(endpoint: string): boolean {
  const cleanPath = endpoint.split("?")[0].replace(/\/+$/, "");
  const normalized = cleanPath.startsWith("/") ? cleanPath : `/${cleanPath}`;
  return PUBLIC_AUTH_PATHS.has(normalized);
}

export class ApiError extends Error {
  public readonly statusCode: number;
  public readonly fieldErrors: Record<string, string[]>;

  constructor(
    message: string,
    statusCode = 400,
    fieldErrors: Record<string, string[]> = {}
  ) {
    super(message);
    this.name = "ApiError";
    this.statusCode = statusCode;
    this.fieldErrors = fieldErrors;
  }
}

export class ApiClient {
  private readonly baseUrl: string;
  private refreshPromise: Promise<string | null> | null = null;

  constructor(baseUrl?: string) {
    this.baseUrl =
      baseUrl ||
      process.env.NEXT_PUBLIC_API_BASE_URL ||
      "http://localhost:8017/api/v1";
  }

  public getBaseUrl(): string {
    return this.getEffectiveBaseUrl();
  }

  public getEffectiveBaseUrl(): string {
    if (typeof window !== "undefined") {
      const pageHost = window.location.hostname;
      // If we are browsing on a remote domain/IP or HTTPS, but baseUrl points to http://localhost,
      // fallback to relative /api/v1 to prevent Mixed Content and NetworkError
      if (
        (window.location.protocol === "https:" && this.baseUrl.startsWith("http://")) ||
        (pageHost !== "localhost" && pageHost !== "127.0.0.1" && this.baseUrl.includes("localhost"))
      ) {
        return "/api/v1";
      }
    }
    return this.baseUrl;
  }

  private buildUrl(
    endpoint: string,
    params?: Record<string, string | number | boolean | undefined | null>
  ): string {
    const rawBase = (this.getEffectiveBaseUrl() || "http://localhost:8017/api/v1").trim();
    const cleanBase = rawBase.replace(/\/+$/, "");
    const cleanEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
    const combinedPath = `${cleanBase}${cleanEndpoint}`.replace(/([^:]\/)\/+/g, "$1");

    const origin =
      typeof window !== "undefined" && window.location?.origin
        ? window.location.origin
        : (process.env.BACKEND_INTERNAL_URL || "http://localhost:3017");

    const url = new URL(combinedPath, origin);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && String(value).trim() !== "") {
          url.searchParams.set(key, String(value));
        }
      });
    }
    return url.toString();
  }

  public setAuthToken(token: string | null) {
    if (typeof window !== "undefined") {
      if (token) {
        localStorage.setItem(ACCESS_TOKEN_KEY, token);
      } else {
        localStorage.removeItem(ACCESS_TOKEN_KEY);
      }
    }
  }

  public setAuthTokens(
    tokens: AuthTokens,
    options?: { rememberMe?: boolean; durationDays?: number }
  ) {
    if (typeof window === "undefined") return;
    if (tokens.access_token) {
      localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
    }
    if (tokens.refresh_token) {
      localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
    }
    const existingMeta = this.getAuthMeta();
    const rememberMe =
      options?.rememberMe ?? tokens.remember_me ?? existingMeta?.rememberMe ?? false;
    const durationDays =
      options?.durationDays ??
      tokens.remember_me_duration_days ??
      existingMeta?.durationDays ??
      30;
    const refreshExpiresAt = tokens.refresh_expires_at
      ? tokens.refresh_expires_at * 1000
      : Date.now() + (tokens.refresh_expires_in || 60 * 60 * 24 * durationDays) * 1000;

    const meta: StoredAuthMeta = {
      rememberMe,
      durationDays,
      refreshExpiresAt,
      updatedAt: Date.now(),
    };
    localStorage.setItem(AUTH_META_KEY, JSON.stringify(meta));
  }

  private getAuthMeta(): StoredAuthMeta | null {
    if (typeof window === "undefined") return null;
    try {
      const raw = localStorage.getItem(AUTH_META_KEY);
      return raw ? (JSON.parse(raw) as StoredAuthMeta) : null;
    } catch {
      return null;
    }
  }

  public getAuthToken(): string | null {
    if (typeof window !== "undefined") {
      return localStorage.getItem(ACCESS_TOKEN_KEY);
    }
    return null;
  }

  public getRefreshToken(): string | null {
    if (typeof window === "undefined") return null;
    const meta = this.getAuthMeta();
    if (meta?.refreshExpiresAt && Date.now() > meta.refreshExpiresAt) {
      this.clearAuth();
      return null;
    }
    const rt = localStorage.getItem(REFRESH_TOKEN_KEY);
    if (!rt) return null;
    if (isJwtExpired(rt, 5)) {
      this.clearAuth();
      return null;
    }
    return rt;
  }

  public setRememberedCredentials(
    loginId: string,
    password: string,
    durationDays: number
  ) {
    if (typeof window === "undefined") return;
    const safeDays = Math.max(1, Math.min(365, durationDays || 30));
    const record: RememberedCredentials = {
      loginId,
      password,
      durationDays: safeDays,
      expiresAt: Date.now() + safeDays * 86400 * 1000,
    };
    localStorage.setItem(REMEMBERED_CREDS_KEY, JSON.stringify(record));
  }

  public getRememberedCredentials(): RememberedCredentials | null {
    if (typeof window === "undefined") return null;
    try {
      const raw = localStorage.getItem(REMEMBERED_CREDS_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw) as RememberedCredentials;
      if (!parsed?.loginId || (parsed.expiresAt && Date.now() > parsed.expiresAt)) {
        localStorage.removeItem(REMEMBERED_CREDS_KEY);
        return null;
      }
      return parsed;
    } catch {
      localStorage.removeItem(REMEMBERED_CREDS_KEY);
      return null;
    }
  }

  public clearRememberedCredentials() {
    if (typeof window !== "undefined") {
      localStorage.removeItem(REMEMBERED_CREDS_KEY);
    }
  }

  public setTenantSlug(slug: string | null) {
    if (typeof window !== "undefined") {
      if (slug) {
        localStorage.setItem(TENANT_SLUG_KEY, slug);
      } else {
        localStorage.removeItem(TENANT_SLUG_KEY);
      }
    }
  }

  public getTenantSlug(): string | null {
    if (typeof window !== "undefined") {
      // Derive client subdomains while leaving platform apex to server-side resolution
      const host = window.location.hostname.toLowerCase();
      if (host.includes(".beamline.musfiqdehan.com") || host.includes(".localhost")) {
        const sub = host.split(".")[0];
        if (sub && sub !== "www" && sub !== "app" && sub !== "api" && sub !== "beamline") return sub;
      }

      // Explicit ?tenant= query parameter (for dev testing & preview links)
      const params = new URLSearchParams(window.location.search);
      const queryTenant = params.get("tenant")?.trim();
      if (queryTenant) return queryTenant;

      // When inside /admin, use the authenticated user's active tenant slug
      const pathname = window.location.pathname;
      if (pathname.startsWith("/admin")) {
        const stored = localStorage.getItem(TENANT_SLUG_KEY);
        if (stored) return stored;
      }
    }
    return null;
  }

  public clearAuth() {
    this.setAuthToken(null);
    if (typeof window !== "undefined") {
      localStorage.removeItem(REFRESH_TOKEN_KEY);
      localStorage.removeItem(AUTH_META_KEY);
    }
  }

  public async refreshAccessToken(): Promise<string | null> {
    if (typeof window === "undefined") return null;
    if (this.refreshPromise) {
      return this.refreshPromise;
    }

    const refreshToken = this.getRefreshToken();
    if (!refreshToken) {
      this.clearAuth();
      return null;
    }

    this.refreshPromise = (async () => {
      try {
        const tenantSlug = this.getTenantSlug();
        const url = this.buildUrl("/auth/refresh/");
        const resp = await fetch(url, {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
            ...(tenantSlug ? { "X-Tenant-Slug": tenantSlug } : {}),
          },
          body: JSON.stringify({ refresh_token: refreshToken }),
          cache: "no-store",
        });

        const rawText = await resp.text();
        let json: ApiEnvelope<{ tokens?: AuthTokens }> | null = null;
        if (rawText && rawText.trim().length > 0) {
          try {
            json = JSON.parse(rawText) as ApiEnvelope<{ tokens?: AuthTokens }>;
          } catch {
            json = null;
          }
        }

        if (resp.ok && json?.success && json.data?.tokens?.access_token) {
          this.setAuthTokens(json.data.tokens);
          return json.data.tokens.access_token;
        }
        this.clearAuth();
        return null;
      } catch {
        return null;
      } finally {
        this.refreshPromise = null;
      }
    })();

    return this.refreshPromise;
  }

  private async resolveRequestToken(isPublicAuth: boolean): Promise<string | null> {
    if (isPublicAuth) return null;
    const token = this.getAuthToken();
    if (token && !isJwtExpired(token, 30)) {
      return token;
    }
    if (this.getRefreshToken()) {
      return this.refreshAccessToken();
    }
    if (token) {
      this.clearAuth();
    }
    return null;
  }

  private buildHeaders(
    token: string | null,
    tenantSlug: string | null,
    includeJsonContentType: boolean,
    extraHeaders?: HeadersInit
  ): Record<string, string> {
    return {
      Accept: "application/json",
      ...(includeJsonContentType ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(tenantSlug ? { "X-Tenant-Slug": tenantSlug } : {}),
      ...((extraHeaders as Record<string, string>) || {}),
    };
  }

  private shouldRetryWithRefresh(
    statusCode: number,
    errorMsg: string,
    isPublicAuth: boolean,
    hasRetried: boolean
  ): boolean {
    if (isPublicAuth || hasRetried) return false;
    return (
      statusCode === 401 ||
      (statusCode === 403 &&
        /expired|invalid token|not authenticated/i.test(errorMsg))
    );
  }

  private async performFetchAndParse<T>(
    url: string,
    options: RequestInit,
    endpoint: string,
    includeJsonContentType: boolean,
    extraHeaders?: HeadersInit,
    hasRetried = false
  ): Promise<ApiEnvelope<T>> {
    const isPublicAuth = isPublicAuthEndpoint(endpoint);
    const tenantSlug = this.getTenantSlug();
    const token = hasRetried
      ? this.getAuthToken()
      : await this.resolveRequestToken(isPublicAuth);
    const headers = this.buildHeaders(
      token,
      tenantSlug,
      includeJsonContentType,
      extraHeaders
    );

    let response: Response;
    try {
      response = await fetch(url, {
        ...options,
        headers,
        cache: "no-store",
      });
    } catch (networkErr) {
      const msg =
        networkErr instanceof Error ? networkErr.message : "Network error";
      throw new ApiError(
        includeJsonContentType
          ? `Network error connecting to API: ${msg}`
          : `Network error uploading file: ${msg}`,
        0
      );
    }

    const rawText = await response.text();
    let json: ApiEnvelope<T> | null = null;
    if (rawText && rawText.trim().length > 0) {
      try {
        json = JSON.parse(rawText) as ApiEnvelope<T>;
      } catch {
        json = null;
      }
    }

    if (!response.ok || !json || json.success === false) {
      const errData = (json?.data as unknown as Record<string, unknown>) || {};
      const rawErrors = (errData.errors as Record<string, unknown>) || {};
      const fieldErrors: Record<string, string[]> = {};
      Object.entries(rawErrors).forEach(([k, v]) => {
        if (Array.isArray(v)) {
          fieldErrors[k] = v.map(String);
        } else if (typeof v === "string") {
          fieldErrors[k] = [v];
        }
      });

      const fallbackMsg = !response.ok
        ? includeJsonContentType
          ? `Request failed with status ${response.status} (${response.statusText || "Server Response"})`
          : `Upload failed with status ${response.status}`
        : "The server returned an invalid or unparseable response.";
      const errorMsg = json?.message || fallbackMsg;

      if (this.shouldRetryWithRefresh(response.status, errorMsg, isPublicAuth, hasRetried)) {
        const refreshedToken = await this.refreshAccessToken();
        if (refreshedToken) {
          return this.performFetchAndParse<T>(
            url,
            options,
            endpoint,
            includeJsonContentType,
            extraHeaders,
            true
          );
        }
        this.clearAuth();
      }

      throw new ApiError(errorMsg, response.status, fieldErrors);
    }
    return json;
  }

  public async request<T>(
    endpoint: string,
    options: RequestInit = {},
    params?: Record<string, string | number | boolean | undefined | null>
  ): Promise<ApiEnvelope<T>> {
    const url = this.buildUrl(endpoint, params);
    return this.performFetchAndParse<T>(
      url,
      options,
      endpoint,
      Boolean(options.body),
      options.headers
    );
  }

  public async listPaginated<T>(
    endpoint: string,
    params?: Record<string, string | number | boolean | undefined | null>
  ): Promise<CursorPaginatedData<T>> {
    const envelope = await this.request<CursorPaginatedData<T>>(
      endpoint,
      { method: "GET" },
      params
    );
    return envelope.data;
  }

  public async get<T>(
    endpoint: string,
    params?: Record<string, string | number | boolean | undefined | null>
  ): Promise<T> {
    const envelope = await this.request<T>(endpoint, { method: "GET" }, params);
    return envelope.data;
  }

  public async post<T, P = Record<string, unknown>>(
    endpoint: string,
    payload?: P
  ): Promise<ApiEnvelope<T>> {
    return this.request<T>(endpoint, {
      method: "POST",
      body: JSON.stringify(payload || {}),
    });
  }

  public async patch<T, P = Record<string, unknown>>(
    endpoint: string,
    payload: P
  ): Promise<ApiEnvelope<T>> {
    return this.request<T>(endpoint, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  }

  public async delete<T = { id: string }>(endpoint: string, payload?: Record<string, unknown>): Promise<ApiEnvelope<T>> {
    return this.request<T>(endpoint, {
      method: "DELETE",
      body: payload ? JSON.stringify(payload) : undefined,
    });
  }

  public async uploadFormData<T>(
    endpoint: string,
    formData: FormData
  ): Promise<ApiEnvelope<T>> {
    const url = this.buildUrl(endpoint);
    return this.performFetchAndParse<T>(
      url,
      {
        method: "POST",
        body: formData,
      },
      endpoint,
      false
    );
  }
}

export const apiClient = new ApiClient();
