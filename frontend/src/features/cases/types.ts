export type CaseStatus = "ACTIVE" | "ARCHIVED" | "CLOSED";

export interface Case {
  id: string;
  workspace_id: string;
  name: string;
  reference_number: string | null;
  description: string | null;
  status: CaseStatus;
  created_by: string;
  created_at: string;
  updated_at: string;
  is_active: boolean;
}

export interface CaseCreateInput {
  name: string;
  reference_number?: string;
  description?: string;
  status?: CaseStatus;
}

export interface CaseUpdateInput {
  name?: string;
  reference_number?: string | null;
  description?: string | null;
  status?: CaseStatus;
}
