import { apiClient } from "../../services/apiClient";
import type { SemanticSearchResponse } from "./types";

export const searchApi = {
  async search(
    workspaceId: string,
    query: string,
    caseId?: string,
    topK = 5,
  ): Promise<SemanticSearchResponse> {
    const { data } = await apiClient.post<SemanticSearchResponse>(
      `/api/v1/workspaces/${workspaceId}/search`,
      { query, case_id: caseId, top_k: topK },
      { timeout: 120_000 },
    );
    return data;
  },
};
