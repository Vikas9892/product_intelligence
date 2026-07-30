import type { AxiosRequestConfig } from "axios";

import { apiClient } from "./client";

/**
 * Thin typed wrappers over the Axios instance — the central request layer every
 * endpoint function builds on. They return the parsed response body directly
 * (not the Axios envelope) and, thanks to the client's response interceptor,
 * reject with an `ApiError` on failure.
 */
export async function apiGet<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const { data } = await apiClient.get<T>(url, config);
  return data;
}

export async function apiPost<T>(
  url: string,
  body?: unknown,
  config?: AxiosRequestConfig,
): Promise<T> {
  const { data } = await apiClient.post<T>(url, body, config);
  return data;
}

export async function apiDelete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const { data } = await apiClient.delete<T>(url, config);
  return data;
}
