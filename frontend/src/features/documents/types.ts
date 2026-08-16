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

export type ExtractionStatus = "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED";

export interface DocumentExtraction {
  id: string;
  document_id: string;
  extractor_type: string;
  extractor_version: string;
  status: ExtractionStatus;
  text_content: string;
  character_count: number;
  page_count: number | null;
  parser_metadata: Record<string, unknown>;
  source_sha256_hash: string;
  extracted_at: string | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export type IndexingStatus = "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED";

export interface DocumentIndex {
  id: string;
  document_id: string;
  status: IndexingStatus;
  embedding_provider: string;
  embedding_model: string;
  embedding_dimension: number;
  indexed_chunk_count: number;
  source_extraction_sha256: string;
  qdrant_collection: string;
  error_code: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SemanticSearchResult {
  chunk_id: string;
  document_id: string;
  case_id: string;
  chunk_index: number;
  content: string;
  score: number;
  page_start: number | null;
  page_end: number | null;
  metadata: Record<string, unknown>;
}

export interface SemanticSearchResponse {
  results: SemanticSearchResult[];
}
