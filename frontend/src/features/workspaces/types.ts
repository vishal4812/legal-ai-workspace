export type WorkspaceRole = "OWNER" | "ADMIN" | "MEMBER" | "VIEWER";

export interface Workspace {
  id: string;
  name: string;
  description: string | null;
  owner_id: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  current_user_role: WorkspaceRole;
}

export interface WorkspaceMember {
  id: string;
  workspace_id: string;
  user_id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  role: WorkspaceRole;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceCreateInput {
  name: string;
  description?: string;
}

export interface WorkspaceUpdateInput {
  name?: string;
  description?: string | null;
  is_active?: boolean;
}

export interface MemberCreateInput {
  email: string;
  role: Exclude<WorkspaceRole, "OWNER">;
}

export interface MemberRoleUpdateInput {
  role: Exclude<WorkspaceRole, "OWNER">;
}
