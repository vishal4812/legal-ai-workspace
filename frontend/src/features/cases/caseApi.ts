import { apiClient } from "../../services/apiClient";
import type { Case, CaseCreateInput, CaseUpdateInput } from "./types";

function basePath(workspaceId: string): string {
  return `/api/v1/workspaces/${workspaceId}/cases`;
}

export const caseApi = {
  async list(workspaceId: string): Promise<Case[]> {
    const { data } = await apiClient.get<Case[]>(basePath(workspaceId));
    return data;
  },

  async create(workspaceId: string, input: CaseCreateInput): Promise<Case> {
    const { data } = await apiClient.post<Case>(basePath(workspaceId), input);
    return data;
  },

  async get(workspaceId: string, caseId: string): Promise<Case> {
    const { data } = await apiClient.get<Case>(
      `${basePath(workspaceId)}/${caseId}`,
    );
    return data;
  },

  async update(
    workspaceId: string,
    caseId: string,
    input: CaseUpdateInput,
  ): Promise<Case> {
    const { data } = await apiClient.patch<Case>(
      `${basePath(workspaceId)}/${caseId}`,
      input,
    );
    return data;
  },

  async archive(workspaceId: string, caseId: string): Promise<Case> {
    const { data } = await apiClient.delete<Case>(
      `${basePath(workspaceId)}/${caseId}`,
    );
    return data;
  },
};
