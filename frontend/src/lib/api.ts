// API client for the DocuForge AI FastAPI backend.
// Configure backend URL via VITE_API_BASE_URL or the in-app settings (localStorage).
import { auth } from "./firebase";

const LS_KEY = "docuforge.apiBaseUrl";

export function getApiBaseUrl(): string {
  const stored = typeof window !== "undefined" ? window.localStorage.getItem(LS_KEY) : null;
  const envBase = (import.meta as any).env?.VITE_API_BASE_URL;
  const sameOrigin = typeof window !== "undefined" ? window.location.origin : null;
  return (
    stored ||
    envBase ||
    sameOrigin ||
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
}

export interface GenerateResponse {
  status: "completed" | "failed" | "processing";
  reportId?: string;
  pdfUrl?: string;
  docxUrl?: string;
  error?: string;
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
    throw new Error(data?.error || data?.detail || `Backend error ${res.status}`);
  }
  return data;
}

export function fileUrl(path: string): string {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  return `${getApiBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
}
