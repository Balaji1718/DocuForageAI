import { useState } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "@/components/AppShell";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "@/hooks/use-toast";
import { ApiError, generateReport } from "@/lib/api";
import { ArrowLeft, Sparkles } from "lucide-react";

const MAX_CONTENT = 100_000; // 100k chars guard
const MAX_FILE_BYTES = 3_000_000;

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const base64 = result.includes(",") ? result.split(",")[1] : "";
      resolve(base64);
    };
    reader.onerror = () => reject(new Error(`Failed to read ${file.name}`));
    reader.readAsDataURL(file);
  });
}

export default function CreateReport() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [rules, setRules] = useState(
    "Use a formal academic tone. Include sections: Abstract, Introduction, Methodology, Results, Discussion, Conclusion, References. Use numbered headings."
  );
  const [content, setContent] = useState("");
  const [referenceContent, setReferenceContent] = useState("");
  const [contentFiles, setContentFiles] = useState<File[]>([]);
  const [referenceFiles, setReferenceFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user) return;
    if (content.length > MAX_CONTENT) {
      toast({
        title: "Content too large",
        description: `Please keep content under ${MAX_CONTENT.toLocaleString()} characters.`,
        variant: "destructive",
      });
      return;
    }

    const allFiles = [...contentFiles, ...referenceFiles];
    const oversized = allFiles.find((f) => f.size > MAX_FILE_BYTES);
    if (oversized) {
      toast({
        title: "File too large",
        description: `${oversized.name} exceeds ${Math.floor(MAX_FILE_BYTES / 1_000_000)}MB limit.`,
        variant: "destructive",
      });
      return;
    }

    setBusy(true);
    try {
      const contentFilePayloads = await Promise.all(
        contentFiles.map(async (file) => ({
          filename: file.name,
          mimeType: file.type || "application/octet-stream",
          contentBase64: await fileToBase64(file),
          role: "content" as const,
        }))
      );
      const referenceFilePayloads = await Promise.all(
        referenceFiles.map(async (file) => ({
          filename: file.name,
          mimeType: file.type || "application/octet-stream",
          contentBase64: await fileToBase64(file),
          role: "reference" as const,
        }))
      );

      const response = await generateReport({
        userId: user.uid,
        title,
        rules,
        content,
        referenceContent,
        referenceMimeType: "text/plain",
        inputFiles: [...contentFilePayloads, ...referenceFilePayloads],
      });

      if (!response.reportId) {
        throw new Error("Backend did not return a report ID.");
      }

      navigate(`/reports/${response.reportId}`);

      if (response.status === "failed") {
        toast({
          title: "Backend error",
          description: response.error ?? "Generation failed.",
          variant: "destructive",
        });
      }
    } catch (err: any) {
      const apiError = err instanceof ApiError ? err : null;
      if (apiError?.reportId) {
        navigate(`/reports/${apiError.reportId}`);
      }

      const qualityDetails = apiError?.qualityErrors?.length
        ? ` ${apiError.qualityErrors.join("; ")}`
        : "";
      toast({
        title: "Report generation failed",
        description: `${err?.message ?? "Could not reach the backend."}${qualityDetails}`,
        variant: "destructive",
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <AppShell>
      <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="mb-4">
        <ArrowLeft className="mr-2 h-4 w-4" /> Back
      </Button>

      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Create Report</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Describe formatting rules and paste your raw content. DocuForge AI compiles a structured PDF & DOCX.
        </p>
      </div>

      <Card className="gradient-card border-border/60 shadow-card">
        <CardContent className="p-6">
          <form onSubmit={submit} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="title">Title</Label>
              <Input
                id="title"
                required
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. The Impact of AI on Modern Education"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="rules">Formatting Rules</Label>
              <Textarea
                id="rules"
                required
                rows={5}
                value={rules}
                onChange={(e) => setRules(e.target.value)}
                placeholder="Describe sections, tone, citation style, formatting requirements…"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="reference">Optional Reference Content</Label>
              <Textarea
                id="reference"
                rows={5}
                value={referenceContent}
                onChange={(e) => setReferenceContent(e.target.value)}
                placeholder="Optional: paste a sample structure you want to mimic (organization only, not wording)."
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="contentFiles">Content Files (optional)</Label>
                <Input
                  id="contentFiles"
                  type="file"
                  multiple
                  accept="*/*"
                  onChange={(e) => setContentFiles(Array.from(e.target.files || []))}
                />
                <p className="text-xs text-muted-foreground">
                  Accepted: text, JSON, CSV, DOCX, PDF, images, and other files. Unsupported binary files are kept as metadata.
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="referenceFiles">Reference Files (optional)</Label>
                <Input
                  id="referenceFiles"
                  type="file"
                  multiple
                  accept="*/*"
                  onChange={(e) => setReferenceFiles(Array.from(e.target.files || []))}
                />
                <p className="text-xs text-muted-foreground">Use this to align output structure with sample documents.</p>
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="content">Content</Label>
                <span className={`text-xs ${content.length > MAX_CONTENT ? "text-destructive" : "text-muted-foreground"}`}>
                  {content.length.toLocaleString()} / {MAX_CONTENT.toLocaleString()}
                </span>
              </div>
              <Textarea
                id="content"
                rows={14}
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="Paste raw notes, sources, data, or a draft. The AI will structure it according to your rules."
                className="font-mono text-sm"
              />
            </div>

            <Button
              type="submit"
              disabled={busy}
              className="w-full gradient-primary text-primary-foreground hover:opacity-90"
            >
              <Sparkles className="mr-2 h-4 w-4" />
              {busy ? "Generating…" : "Generate Report"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </AppShell>
  );
}
