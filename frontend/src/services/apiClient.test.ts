import axios, { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from "axios";
import { afterEach, expect, test, vi } from "vitest";

import {
  installAuthInterceptors,
  setAccessToken,
  setAuthFailureHandler,
} from "./apiClient";

function response(config: InternalAxiosRequestConfig, status: number): AxiosResponse {
  return {
    data: status === 200 ? { ok: true } : { detail: "Unauthorized" },
    status,
    statusText: status === 200 ? "OK" : "Unauthorized",
    headers: {},
    config,
  };
}

function unauthorized(config: InternalAxiosRequestConfig) {
  return new AxiosError(
    "Unauthorized",
    AxiosError.ERR_BAD_REQUEST,
    config,
    undefined,
    response(config, 401),
  );
}

afterEach(() => {
  setAccessToken(null);
  setAuthFailureHandler(null);
});

test("a 401 refreshes once and retries the original request", async () => {
  const client = axios.create();
  let attempts = 0;
  client.defaults.adapter = async (config) => {
    attempts += 1;
    if (attempts === 1) throw unauthorized(config);
    return response(config, 200);
  };
  const refresh = vi.fn().mockResolvedValue("rotated-access-token");
  const uninstall = installAuthInterceptors(client, refresh);

  const result = await client.get("/protected");

  expect(result.status).toBe(200);
  expect(attempts).toBe(2);
  expect(refresh).toHaveBeenCalledOnce();
  uninstall();
});

test("a failed retried request does not enter an infinite refresh loop", async () => {
  const client = axios.create();
  let attempts = 0;
  client.defaults.adapter = async (config) => {
    attempts += 1;
    throw unauthorized(config);
  };
  const refresh = vi.fn().mockResolvedValue("still-invalid-access-token");
  const onFailure = vi.fn();
  setAuthFailureHandler(onFailure);
  const uninstall = installAuthInterceptors(client, refresh);

  await expect(client.get("/protected")).rejects.toBeInstanceOf(AxiosError);

  expect(attempts).toBe(2);
  expect(refresh).toHaveBeenCalledOnce();
  expect(onFailure).toHaveBeenCalledOnce();
  uninstall();
});
