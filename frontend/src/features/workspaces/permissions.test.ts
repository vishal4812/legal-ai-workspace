import { describe, expect, test } from "vitest";

import {
  canArchiveCases,
  canChangeMemberRoles,
  canCreateOrEditCases,
  canManageMembers,
  canUpdateWorkspace,
} from "./permissions";

describe("workspace role permissions", () => {
  test("owner has every Phase 3 permission", () => {
    expect(canUpdateWorkspace("OWNER")).toBe(true);
    expect(canManageMembers("OWNER")).toBe(true);
    expect(canChangeMemberRoles("OWNER")).toBe(true);
    expect(canCreateOrEditCases("OWNER")).toBe(true);
    expect(canArchiveCases("OWNER")).toBe(true);
  });

  test("admin cannot transfer roles but can manage members and cases", () => {
    expect(canUpdateWorkspace("ADMIN")).toBe(true);
    expect(canManageMembers("ADMIN")).toBe(true);
    expect(canChangeMemberRoles("ADMIN")).toBe(false);
    expect(canCreateOrEditCases("ADMIN")).toBe(true);
    expect(canArchiveCases("ADMIN")).toBe(true);
  });

  test("member can create and edit cases only", () => {
    expect(canUpdateWorkspace("MEMBER")).toBe(false);
    expect(canManageMembers("MEMBER")).toBe(false);
    expect(canCreateOrEditCases("MEMBER")).toBe(true);
    expect(canArchiveCases("MEMBER")).toBe(false);
  });

  test("viewer receives read-only UI permissions", () => {
    expect(canUpdateWorkspace("VIEWER")).toBe(false);
    expect(canManageMembers("VIEWER")).toBe(false);
    expect(canChangeMemberRoles("VIEWER")).toBe(false);
    expect(canCreateOrEditCases("VIEWER")).toBe(false);
    expect(canArchiveCases("VIEWER")).toBe(false);
  });
});
