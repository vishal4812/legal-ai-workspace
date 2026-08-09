import { apiClient } from "../../services/apiClient";
import type {
  MemberCreateInput,
  MemberRoleUpdateInput,
  Workspace,
  WorkspaceCreateInput,
  WorkspaceMember,
  WorkspaceUpdateInput,
} from "./types";

export const workspaceApi = {
  async list(): Promise<Workspace[]> {
    const { data } = await apiClient.get<Workspace[]>("/api/v1/workspaces");
    return data;
  },

  async create(input: WorkspaceCreateInput): Promise<Workspace> {
    const { data } = await apiClient.post<Workspace>("/api/v1/workspaces", input);
    return data;
  },

  async get(workspaceId: string): Promise<Workspace> {
    const { data } = await apiClient.get<Workspace>(
      `/api/v1/workspaces/${workspaceId}`,
    );
    return data;
  },

  async update(workspaceId: string, input: WorkspaceUpdateInput): Promise<Workspace> {
    const { data } = await apiClient.patch<Workspace>(
      `/api/v1/workspaces/${workspaceId}`,
      input,
    );
    return data;
  },

  async archive(workspaceId: string): Promise<Workspace> {
    const { data } = await apiClient.delete<Workspace>(
      `/api/v1/workspaces/${workspaceId}`,
    );
    return data;
  },
};

export const membershipApi = {
  async list(workspaceId: string): Promise<WorkspaceMember[]> {
    const { data } = await apiClient.get<WorkspaceMember[]>(
      `/api/v1/workspaces/${workspaceId}/members`,
    );
    return data;
  },

  async add(workspaceId: string, input: MemberCreateInput): Promise<WorkspaceMember> {
    const { data } = await apiClient.post<WorkspaceMember>(
      `/api/v1/workspaces/${workspaceId}/members`,
      input,
    );
    return data;
  },

  async changeRole(
    workspaceId: string,
    userId: string,
    input: MemberRoleUpdateInput,
  ): Promise<WorkspaceMember> {
    const { data } = await apiClient.patch<WorkspaceMember>(
      `/api/v1/workspaces/${workspaceId}/members/${userId}`,
      input,
    );
    return data;
  },

  async remove(workspaceId: string, userId: string): Promise<void> {
    await apiClient.delete(
      `/api/v1/workspaces/${workspaceId}/members/${userId}`,
    );
  },
};
