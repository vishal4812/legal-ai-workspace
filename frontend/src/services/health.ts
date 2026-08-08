import { useQuery } from "@tanstack/react-query";

import type { HealthResponse } from "../types/api";
import { apiClient } from "./apiClient";

async function getHealth(): Promise<HealthResponse> {
  const response = await apiClient.get<HealthResponse>("/health");
  return response.data;
}

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: getHealth });
}
