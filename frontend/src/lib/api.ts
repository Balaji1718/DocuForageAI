// API client for the DocuForge AI FastAPI backend.
// Configure backend URL via VITE_API_BASE_URL or the in-app settings (localStorage).
import { auth } from "./firebase";

const LS_KEY = "docuforge.apiBaseUrl";

export function getApiBaseUrl(): string {
  const stored = typeof window !== "undefined" ? window.localStorage.getItem(LS_KEY) : null;
  const envBase = (import.meta as any).env?.VITE_API_BASE_URL;
  const sameOrigin = typeof window !== "undefined" ? window.location.origin : null;
  const sameOriginIsBackend =
    typeof window !== "undefined" &&
    (() => {
      try {
        const parsed = new URL(window.location.origin);
        return parsed.port === "8000" || parsed.pathname === "/";
      } catch {
        return false;
      }
    })();
  return (
    stored ||
    envBase ||
    (sameOriginIsBackend ? sameOrigin : null) ||
    "http://localhost:8000"
  );
}

export function setApiBaseUrl(url: string) {
  window.localStorage.setItem(LS_KEY, url.replace(/\/$/, ""));
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
  content: string;
  referenceContent?: string;
  referenceMimeType?: string;
  inputFiles?: InputFilePayload[];
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

export function fileUrl(path: string): string {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  return `${getApiBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
}
