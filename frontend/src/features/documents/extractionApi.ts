import { isAxiosError } from "axios";

import { apiClient } from "../../services/apiClient";
import type { DocumentExtraction } from "./types";

function extractionPath(workspaceId: string, caseId: string, documentId: string): string {
  return (
    `/api/v1/workspaces/${workspaceId}/cases/${caseId}/documents/` +
    `${documentId}/extraction`
  );
}

export const extractionApi = {
  async get(
    workspaceId: string,
    caseId: string,
    documentId: string,
  ): Promise<DocumentExtraction> {
    const { data } = await apiClient.get<DocumentExtraction>(
      extractionPath(workspaceId, caseId, documentId),
    );
    return data;
  },

  async getOrNull(
    workspaceId: string,
    caseId: string,
    documentId: string,
  ): Promise<DocumentExtraction | null> {
    try {
      return await this.get(workspaceId, caseId, documentId);
    } catch (error) {
      if (isAxiosError(error) && error.response?.status === 404) return null;
      throw error;
    }
  },

  async extract(
    workspaceId: string,
    caseId: string,
    documentId: string,
  ): Promise<DocumentExtraction> {
    const path = extractionPath(workspaceId, caseId, documentId).replace(
      /\/extraction$/,
      "/extract",
    );
    const { data } = await apiClient.post<DocumentExtraction>(path, undefined, {
      timeout: 120_000,
    });
    return data;
  },
};
