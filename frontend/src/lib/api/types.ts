/**
 * Ergonomic aliases over the generated OpenAPI schema (`schema.d.ts`).
 *
 * The generated file is the single source of truth (regenerate with
 * `npm run gen:api`); this module just gives the rest of the app short,
 * stable names instead of `components["schemas"]["…"]` everywhere. If the
 * backend contract changes, regeneration makes the mismatch a compile error
 * here — no hand-maintained models to drift.
 */
import type { components } from "./schema";

type Schemas = components["schemas"];

// Products / upload / jobs
export type ProductCreate = Schemas["ProductCreate"];
export type UploadResponse = Schemas["UploadResponse"];
export type UploadAcceptedResponse = Schemas["UploadAcceptedResponse"];
export type JobStatusResponse = Schemas["JobStatusResponse"];
export type ProductSummary = Schemas["ProductSummary"];
export type ProductBatchResponse = Schemas["ProductBatchResponse"];

// Search
export type ProductSearchResponse = Schemas["ProductSearchResponse"];
export type ProductSearchResult = Schemas["ProductSearchResult"];

// Recommendations
export type RecommendationsResponse = Schemas["RecommendationsResponse"];
export type RecommendationInfo = Schemas["RecommendationInfo"];

// Duplicate detection / verification
export type DuplicateCheckResponse = Schemas["DuplicateCheckResponse"];
export type DuplicateCandidateInfo = Schemas["DuplicateCandidateInfo"];

// Pricing
export type PricingRequest = Schemas["PricingRequest"];
export type PricingResponse = Schemas["PricingResponse"];
export type ComparableProductInfo = Schemas["ComparableProductInfo"];

// Explanations
export type ExplanationResponse = Schemas["ExplanationResponse"];
export type TraceBundleResponse = Schemas["TraceBundleResponse"];
export type ProductExplanationsResponse = Schemas["ProductExplanationsResponse"];

// Evaluation
export type EvaluationRunRequest = Schemas["EvaluationRunRequest"];
export type EvaluationRunResponse = Schemas["EvaluationRunResponse"];
export type RerankComparisonResponse = Schemas["RerankComparisonResponse"];

// Models
export type ModelInfoResponse = Schemas["ModelInfoResponse"];

// Analytics
export type DashboardResponse = Schemas["DashboardResponse"];
export type ModelAnalyticsResponse = Schemas["ModelAnalyticsResponse"];
export type AnalyticsReportResponse = Schemas["AnalyticsReportResponse"];
export type UsageMetricsInfo = Schemas["UsageMetricsInfo"];
// Note: the `/analytics/trends` endpoint declares no response_model on the
// backend (it also supports CSV export), so it has no generated schema; its
// response is typed per-call in the analytics feature stage.

// System / ops
export type SystemHealthResponse = Schemas["SystemHealthResponse"];
export type SystemStatsResponse = Schemas["SystemStatsResponse"];
export type VersionResponse = Schemas["VersionResponse"];

// Enterprise (only present when the backend enterprise layer is enabled)
export type OrganizationInfo = Schemas["OrganizationInfo"];
export type OrganizationBootstrapResponse = Schemas["OrganizationBootstrapResponse"];
export type ApiKeyInfo = Schemas["ApiKeyInfo"];
export type ApiKeyCreateRequest = Schemas["ApiKeyCreateRequest"];
export type ApiKeyCreationResponse = Schemas["ApiKeyCreationResponse"];
export type AuditEventInfo = Schemas["AuditEventInfo"];
export type UsageResponse = Schemas["UsageResponse"];
