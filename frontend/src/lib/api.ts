// API client for the DocuForge AI FastAPI backend.
// Configure backend URL via VITE_API_BASE_URL.
import { auth } from "./firebase";

function isLikelyBackendOrigin(origin: string): boolean {
  try {
    const parsed = new URL(origin);
    const host = parsed.hostname.toLowerCase();
    const port = parsed.port;

    // Local development: backend is commonly run on 8000 or 8006.
    if (host === "localhost" || host === "127.0.0.1") {
      return port === "8000" || port === "8006";
    }

    // In deployed environments (80/443 or custom domain), same-origin backend is valid.
    return true;
  } catch {
    return false;
  }
}

export function getApiBaseUrl(): string {
  const envBase = import.meta.env.VITE_API_BASE_URL;
  const sameOrigin = typeof window !== "undefined" ? window.location.origin : "";
  const sameOriginIsBackend =
    typeof window !== "undefined" &&
    isLikelyBackendOrigin(window.location.origin);

  if (envBase) {
    return String(envBase).replace(/\/$/, "");
  }

  if (sameOriginIsBackend && sameOrigin) {
    return sameOrigin;
  }

  return "http://localhost:8000";
}

async function authHeader(): Promise<Record<string, string>> {
  const user = auth.currentUser;
  if (!user) return {};
  const token = await user.getIdToken();
  return { Authorization: `Bearer ${token}` };
}

export interface GenerateRequest {
  userId: string;
  title: string;
  rules: string;
  rulesId?: string;
  content: string;
  referenceContent?: string;
  referenceMimeType?: string;
  inputFiles?: InputFilePayload[];
  metadata?: Record<string, string>;
  sections?: Array<{
    title: string;
    mode: "auto_generate" | "user_provides" | "skip";
  }>;
  ruleOverrides?: Record<string, string | number>;
}

export interface ExtractRulesResponse {
  success: boolean;
  rules_id: string;
  message?: string;
  validation?: {
    is_valid: boolean;
    warnings: string[];
  };
  rules_summary?: {
    page_width?: string;
    page_height?: string;
    margins?: {
      top?: string;
      left?: string;
    };
    body_font?: string;
    body_size?: string;
    sections_detected?: number;
    tables_found?: number;
    confidence?: string;
  };
}

export interface InputFilePayload {
  filename: string;
  mimeType: string;
  contentBase64: string;
  role?: "content" | "reference";
}

export interface GenerateResponse {
  status: "completed" | "failed" | "processing";
  reportId?: string;
  pdfUrl?: string;
  docxUrl?: string;
  error?: string;
  errorCode?: string;
  qualityFailure?: boolean;
  qualityErrors?: string[];
  structuredFeedback?: {
    score?: number;
    issues?: Array<string | { message?: string; severity?: string }>;
    suggestions?: string[];
  };
}

export interface DeleteReportResponse {
  status: "deleted";
  reportId: string;
  removedFiles?: string[];
}

export class ApiError extends Error {
  reportId?: string;
  errorCode?: string;
  qualityFailure?: boolean;
  qualityErrors?: string[];

  constructor(message: string, data?: Partial<GenerateResponse>) {
    super(message);
    this.name = "ApiError";
    this.reportId = data?.reportId;
    this.errorCode = data?.errorCode;
    this.qualityFailure = data?.qualityFailure;
    this.qualityErrors = data?.qualityErrors;
  }
}

export async function generateReport(payload: GenerateRequest): Promise<GenerateResponse> {
  const headers = { "Content-Type": "application/json", ...(await authHeader()) };
  const res = await fetch(`${getApiBaseUrl()}/generate`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(data?.error || data?.detail || `Backend error ${res.status}`, data);
  }
  return data;
}

export async function extractRulesFromDocx(params: {
  file: File;
  documentType?: string;
  notes?: string;
}): Promise<ExtractRulesResponse> {
  const form = new FormData();
  form.append("file", params.file);
  form.append("document_type", params.documentType || "generic");
  form.append("notes", params.notes || "");

  const headers = await authHeader();
  const res = await fetch(`${getApiBaseUrl()}/extract-rules`, {
    method: "POST",
    headers,
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(data?.error || data?.detail || `Backend error ${res.status}`);
  }
  return data as ExtractRulesResponse;
}

export async function deleteReportHistory(reportId: string): Promise<DeleteReportResponse> {
  const headers = await authHeader();
  const res = await fetch(`${getApiBaseUrl()}/reports/${encodeURIComponent(reportId)}`, {
    method: "DELETE",
    headers,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(data?.error || data?.detail || `Backend error ${res.status}`);
  }
  return data as DeleteReportResponse;
}

export function fileUrl(path: string): string {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  return `${getApiBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
}
