import { apiClient } from "../../services/apiClient";
import type { Document, DocumentUploadResponse, UploadProgressHandler } from "./types";

function basePath(workspaceId: string, caseId: string): string {
  return `/api/v1/workspaces/${workspaceId}/cases/${caseId}/documents`;
}

export const documentApi = {
  async list(workspaceId: string, caseId: string): Promise<Document[]> {
    const { data } = await apiClient.get<Document[]>(basePath(workspaceId, caseId));
    return data;
  },

  async get(workspaceId: string, caseId: string, documentId: string): Promise<Document> {
    const { data } = await apiClient.get<Document>(
      `${basePath(workspaceId, caseId)}/${documentId}`,
    );
    return data;
  },

  async upload(
    workspaceId: string,
    caseId: string,
    file: File,
    onProgress?: UploadProgressHandler,
  ): Promise<DocumentUploadResponse> {
    const form = new FormData();
    form.append("file", file, file.name);
    const { data } = await apiClient.post<DocumentUploadResponse>(
      basePath(workspaceId, caseId),
      form,
      {
        timeout: 120_000,
        onUploadProgress: (event) => {
          if (event.total && onProgress) {
            onProgress(Math.min(100, Math.round((event.loaded * 100) / event.total)));
          }
        },
      },
    );
    return data;
  },

  async download(workspaceId: string, caseId: string, documentId: string): Promise<Blob> {
    const { data } = await apiClient.get<Blob>(
      `${basePath(workspaceId, caseId)}/${documentId}/download`,
      { responseType: "blob", timeout: 120_000 },
    );
    return data;
  },

  async archive(workspaceId: string, caseId: string, documentId: string): Promise<Document> {
    const { data } = await apiClient.delete<Document>(
      `${basePath(workspaceId, caseId)}/${documentId}`,
    );
    return data;
  },
};
