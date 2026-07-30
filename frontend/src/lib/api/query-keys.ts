/**
 * Centralized React Query keys.
 *
 * Defining every key here (rather than inline at call sites) keeps cache reads
 * and mutation invalidations referring to the exact same tuples, so a feature
 * can invalidate precisely what it changed. Feature stages add their keys here.
 */
export const queryKeys = {
  health: ["health"] as const,
  version: ["version"] as const,
  system: {
    health: ["system", "health"] as const,
    stats: ["system", "stats"] as const,
  },
  products: {
    status: (id: string) => ["products", "status", id] as const,
    recommendations: (id: string) => ["products", "recommendations", id] as const,
    explanations: (id: string) => ["products", "explanations", id] as const,
    // Metadata carried from a search result (no get-one endpoint exists).
    meta: (id: string) => ["products", "meta", id] as const,
  },
  search: (params: Record<string, unknown>) => ["search", params] as const,
  pricing: {
    byId: (id: string) => ["pricing", id] as const,
  },
  models: {
    list: ["models"] as const,
  },
  analytics: {
    dashboard: ["analytics", "dashboard"] as const,
    models: ["analytics", "models"] as const,
    pipeline: ["analytics", "pipeline"] as const,
    trends: (params: Record<string, unknown>) => ["analytics", "trends", params] as const,
  },
  enterprise: {
    organizations: ["enterprise", "organizations"] as const,
    apiKeys: ["enterprise", "api-keys"] as const,
    audit: ["enterprise", "audit"] as const,
    usage: ["enterprise", "usage"] as const,
  },
} as const;
