import { isAxiosError } from "axios";

const statusMessages: Record<number, string> = {
  401: "Your session has expired. Please sign in again.",
  403: "You do not have permission to perform this action.",
  404: "The requested workspace or case was not found.",
  409: "That change conflicts with the current workspace state.",
  413: "The selected document is too large.",
  415: "Only valid PDF and DOCX documents are supported.",
  422: "Please check the submitted information.",
};

export function apiErrorMessage(error: unknown): string {
  if (isAxiosError<{ detail?: string }>(error)) {
    const status = error.response?.status;
    return error.response?.data?.detail ??
      (status ? statusMessages[status] : undefined) ??
      "The request could not be completed.";
  }
  return error instanceof Error ? error.message : "The request could not be completed.";
}
