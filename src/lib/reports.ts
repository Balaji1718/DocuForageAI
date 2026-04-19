import {
  addDoc,
  collection,
  doc,
  getDoc,
  getDocs,
  onSnapshot,
  orderBy,
  query,
  serverTimestamp,
  updateDoc,
  where,
  Timestamp,
} from "firebase/firestore";
import { db } from "./firebase";

export type ReportStatus = "pending" | "processing" | "completed" | "failed";

export interface Report {
  id: string;
  userId: string;
  title: string;
  rules: string;
  content: string;
  status: ReportStatus;
  pdfUrl?: string;
  docxUrl?: string;
  error?: string;
  createdAt?: Timestamp;
  updatedAt?: Timestamp;
}

export async function createReport(input: {
  userId: string;
  title: string;
  rules: string;
  content: string;
}): Promise<string> {
  const ref = await addDoc(collection(db, "reports"), {
    ...input,
    status: "pending" as ReportStatus,
    pdfUrl: "",
    docxUrl: "",
    createdAt: serverTimestamp(),
    updatedAt: serverTimestamp(),
  });
  return ref.id;
}

export async function updateReport(id: string, patch: Partial<Report>) {
  await updateDoc(doc(db, "reports", id), {
    ...patch,
    updatedAt: serverTimestamp(),
  });
}

export async function getReport(id: string): Promise<Report | null> {
  const snap = await getDoc(doc(db, "reports", id));
  if (!snap.exists()) return null;
  return { id: snap.id, ...(snap.data() as Omit<Report, "id">) };
}

export async function listReports(userId: string): Promise<Report[]> {
  // Avoid composite index requirement: query by userId, sort client-side.
  const q = query(collection(db, "reports"), where("userId", "==", userId));
  const snap = await getDocs(q);
  const items = snap.docs.map((d) => ({ id: d.id, ...(d.data() as Omit<Report, "id">) }));
  items.sort((a, b) => {
    const at = a.createdAt?.toMillis?.() ?? 0;
    const bt = b.createdAt?.toMillis?.() ?? 0;
    return bt - at;
  });
  return items;
}

export function subscribeReport(id: string, cb: (r: Report | null) => void) {
  return onSnapshot(doc(db, "reports", id), (snap) => {
    if (!snap.exists()) cb(null);
    else cb({ id: snap.id, ...(snap.data() as Omit<Report, "id">) });
  });
}

export async function ensureUserDoc(userId: string, email: string, name?: string) {
  const ref = doc(db, "users", userId);
  const snap = await getDoc(ref);
  if (!snap.exists()) {
    const { setDoc } = await import("firebase/firestore");
    await setDoc(ref, {
      email,
      name: name || email.split("@")[0],
      createdAt: serverTimestamp(),
    });
  }
}
