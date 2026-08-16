import { isAxiosError } from "axios";

import { apiClient } from "../../services/apiClient";
import type { DocumentIndex } from "./types";

function indexPath(workspaceId: string, caseId: string, documentId: string): string {
  return `/api/v1/workspaces/${workspaceId}/cases/${caseId}/documents/${documentId}/index`;
}

export const indexingApi = {
  async get(workspaceId: string, caseId: string, documentId: string): Promise<DocumentIndex> {
    const { data } = await apiClient.get<DocumentIndex>(indexPath(workspaceId, caseId, documentId));
    return data;
  },

  async getOrNull(workspaceId: string, caseId: string, documentId: string): Promise<DocumentIndex | null> {
    try {
      return await this.get(workspaceId, caseId, documentId);
    } catch (error) {
      if (isAxiosError(error) && error.response?.status === 404) return null;
      throw error;
    }
  },

  async index(workspaceId: string, caseId: string, documentId: string): Promise<DocumentIndex> {
    const { data } = await apiClient.post<DocumentIndex>(
      indexPath(workspaceId, caseId, documentId),
      undefined,
      { timeout: 300_000 },
    );
    return data;
  },
};
