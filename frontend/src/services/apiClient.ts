import axios, { AxiosHeaders, type AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from "axios";

import type { TokenResponse } from "../features/auth/types";

const baseURL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

let accessToken: string | null = null;
let authFailureHandler: (() => void) | null = null;
let explicitRefresh: Promise<string> | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken() {
  return accessToken;
}

export function setAuthFailureHandler(handler: (() => void) | null) {
  authFailureHandler = handler;
}

const refreshClient = axios.create({
  baseURL,
  headers: { Accept: "application/json" },
  timeout: 10_000,
  withCredentials: true,
});

export async function refreshAccessToken(): Promise<string> {
  if (!explicitRefresh) {
    explicitRefresh = refreshClient
      .post<TokenResponse>("/api/v1/auth/refresh")
      .then(({ data }) => {
        setAccessToken(data.access_token);
        return data.access_token;
      })
      .finally(() => {
        explicitRefresh = null;
      });
  }
  return explicitRefresh;
}

interface RetryableRequest extends InternalAxiosRequestConfig {
  _authRetry?: boolean;
}

function isAuthenticationEntryPoint(url?: string) {
  return ["/auth/login", "/auth/register", "/auth/refresh", "/auth/logout"].some((path) =>
    url?.includes(path),
  );
}

export function installAuthInterceptors(
  client: AxiosInstance,
  refresh: () => Promise<string> = refreshAccessToken,
) {
  let refreshInFlight: Promise<string> | null = null;

  const requestInterceptor = client.interceptors.request.use((config) => {
    if (accessToken) {
      config.headers = AxiosHeaders.from(config.headers);
      config.headers.set("Authorization", `Bearer ${accessToken}`);
    }
    return config;
  });

  const responseInterceptor = client.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
      const request = error.config as RetryableRequest | undefined;
      if (error.response?.status !== 401 || !request || isAuthenticationEntryPoint(request.url)) {
        return Promise.reject(error);
      }
      if (request._authRetry) {
        setAccessToken(null);
        authFailureHandler?.();
        return Promise.reject(error);
      }

      request._authRetry = true;
      try {
        refreshInFlight ??= refresh().finally(() => {
          refreshInFlight = null;
        });
        const token = await refreshInFlight;
        request.headers = AxiosHeaders.from(request.headers);
        request.headers.set("Authorization", `Bearer ${token}`);
        return client(request);
      } catch (refreshError) {
        setAccessToken(null);
        authFailureHandler?.();
        return Promise.reject(refreshError);
      }
    },
  );

  return () => {
    client.interceptors.request.eject(requestInterceptor);
    client.interceptors.response.eject(responseInterceptor);
  };
}

export const apiClient = axios.create({
  baseURL,
  headers: { Accept: "application/json" },
  timeout: 10_000,
  withCredentials: true,
});

installAuthInterceptors(apiClient);
