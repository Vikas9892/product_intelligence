import { API_PREFIX } from "../client";
import { apiDelete, apiGet, apiPost } from "../http";
import type {
  ApiKeyCreateRequest,
  ApiKeyCreationResponse,
  ApiKeyInfo,
  AuditEventInfo,
  OrganizationBootstrapResponse,
  OrganizationInfo,
  UsageResponse,
} from "../types";

/**
 * Enterprise endpoints (mounted only when `ENTERPRISE__ENABLED` is on, so every
 * one of these 404s otherwise — see `features/enterprise/capability.ts`).
 *
 * This is the complete surface. There is deliberately no rotate/update call
 * because the backend exposes none: an API key can be created, listed, and
 * revoked, and that is all.
 */

/**
 * Bootstrap an organization, its default tenant, and an initial OWNER key.
 * The **only** unauthenticated enterprise endpoint. The returned raw key is
 * shown once and never retrievable again.
 */
export function bootstrapOrganization(name: string): Promise<OrganizationBootstrapResponse> {
  return apiPost<OrganizationBootstrapResponse>(`${API_PREFIX}/organizations`, { name });
}

/** List organizations. Requires the manage-organization permission (owner). */
export function listOrganizations(): Promise<OrganizationInfo[]> {
  return apiGet<OrganizationInfo[]>(`${API_PREFIX}/organizations`);
}

/**
 * Create an API key for the caller's tenant. The response carries the raw
 * `key` exactly once; subsequent list calls return metadata only.
 *
 * The backend refuses to mint a key whose role outranks the caller's, so this
 * can legitimately 403 even for an admin.
 */
export function createApiKey(request: ApiKeyCreateRequest): Promise<ApiKeyCreationResponse> {
  return apiPost<ApiKeyCreationResponse>(`${API_PREFIX}/api-keys`, request);
}

/** List the caller's tenant's API keys. Metadata only — never the secret. */
export function listApiKeys(): Promise<ApiKeyInfo[]> {
  return apiGet<ApiKeyInfo[]>(`${API_PREFIX}/api-keys`);
}

/**
 * Revoke one of the caller's tenant's keys by prefix. 404s for a prefix that
 * belongs to another tenant, so callers cannot probe across tenants.
 */
export function revokeApiKey(prefix: string): Promise<ApiKeyInfo> {
  return apiDelete<ApiKeyInfo>(`${API_PREFIX}/api-keys/${encodeURIComponent(prefix)}`);
}

/** The tenant's most recent audit events, newest first. */
export function listAuditEvents(limit = 100): Promise<AuditEventInfo[]> {
  return apiGet<AuditEventInfo[]>(`${API_PREFIX}/audit?limit=${limit}`);
}

/** The tenant's requests-today count and its configured quotas. */
export function getUsage(): Promise<UsageResponse> {
  return apiGet<UsageResponse>(`${API_PREFIX}/usage`);
}
