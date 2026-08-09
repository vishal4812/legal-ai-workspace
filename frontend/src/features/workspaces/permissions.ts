import type { WorkspaceRole } from "./types";

export function canUpdateWorkspace(role: WorkspaceRole): boolean {
  return role === "OWNER" || role === "ADMIN";
}

export function canManageMembers(role: WorkspaceRole): boolean {
  return role === "OWNER" || role === "ADMIN";
}

export function canChangeMemberRoles(role: WorkspaceRole): boolean {
  return role === "OWNER";
}

export function canCreateOrEditCases(role: WorkspaceRole): boolean {
  return role === "OWNER" || role === "ADMIN" || role === "MEMBER";
}

export function canArchiveCases(role: WorkspaceRole): boolean {
  return role === "OWNER" || role === "ADMIN";
}
