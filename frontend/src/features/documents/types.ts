export type DocumentStatus = "UPLOADED";

export interface Document {
  id: string;
  case_id: string;
  original_filename: string;
  mime_type: string;
  file_size: number;
  sha256_hash: string;
  status: DocumentStatus;
  is_active: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export type DocumentUploadResponse = Document;

export type UploadProgressHandler = (percentage: number) => void;
