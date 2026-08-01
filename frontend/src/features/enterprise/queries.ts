"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { queryKeys } from "@/lib/api";
import {
  bootstrapOrganization,
  createApiKey,
  getUsage,
  listApiKeys,
  listAuditEvents,
  revokeApiKey,
} from "@/lib/api/endpoints/enterprise";
import type { ApiKeyCreateRequest } from "@/lib/api/types";

import {
  capabilityFromError,
  capabilityFromSuccess,
  type CapabilityProbeResult,
} from "./capability";

/**
 * Probes what the enterprise layer is doing, using `GET /usage` as the canary.
 *
 * `/usage` is chosen deliberately: it is mounted with the rest of the
 * enterprise router, and it needs only VIEW_USAGE, so the probe distinguishes
 * all four states without side effects. Note the query never *rejects* — the
 * error is mapped into data, because "the request failed" is exactly the
 * signal we want rather than an exception.
 *
 * `retry: false` matters: a 404 here is a legitimate answer, not a transient
 * fault to retry.
 */
export function useEnterpriseCapability() {
  return useQuery<CapabilityProbeResult>({
    queryKey: queryKeys.enterprise.capability,
    queryFn: async () => {
      try {
        await getUsage();
        return capabilityFromSuccess();
      } catch (error) {
        return capabilityFromError(error);
      }
    },
    retry: false,
    staleTime: 30_000,
  });
}

/** The tenant's usage and quota. Only meaningful when authenticated. */
export function useUsage(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.enterprise.usage,
    queryFn: getUsage,
    enabled: options?.enabled ?? true,
    retry: false,
  });
}

/** The tenant's API keys (metadata only — the backend never re-exposes secrets). */
export function useApiKeys(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.enterprise.apiKeys,
    queryFn: listApiKeys,
    enabled: options?.enabled ?? true,
    retry: false,
  });
}

/** The tenant's audit log, newest first. */
export function useAuditEvents(limit = 100, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: [...queryKeys.enterprise.audit, limit],
    queryFn: () => listAuditEvents(limit),
    enabled: options?.enabled ?? true,
    retry: false,
  });
}

/**
 * Bootstrap a new organization. The response contains the one-time owner key;
 * the caller is responsible for showing it once and then dropping it.
 */
export function useBootstrapOrganization() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => bootstrapOrganization(name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.enterprise.capability });
    },
  });
}

/** Create an API key, invalidating the list so the new key appears. */
export function useCreateApiKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: ApiKeyCreateRequest) => createApiKey(request),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.enterprise.apiKeys });
      void queryClient.invalidateQueries({ queryKey: queryKeys.enterprise.audit });
    },
  });
}

/** Revoke an API key by prefix. */
export function useRevokeApiKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (prefix: string) => revokeApiKey(prefix),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.enterprise.apiKeys });
      void queryClient.invalidateQueries({ queryKey: queryKeys.enterprise.audit });
    },
  });
}
