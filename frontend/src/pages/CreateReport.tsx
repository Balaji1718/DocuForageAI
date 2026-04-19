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
import { createReport, updateReport } from "@/lib/reports";
import { generateReport } from "@/lib/api";
import { ArrowLeft, Sparkles } from "lucide-react";

const MAX_CONTENT = 100_000; // 100k chars guard

export default function CreateReport() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [rules, setRules] = useState(
    "Use a formal academic tone. Include sections: Abstract, Introduction, Methodology, Results, Discussion, Conclusion, References. Use numbered headings."
  );
  const [content, setContent] = useState("");
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
    setBusy(true);
    let reportId = "";
    try {
      reportId = await createReport({ userId: user.uid, title, rules, content });
      navigate(`/reports/${reportId}`);
      // Fire backend job (best-effort). Backend also updates Firestore status.
      try {
        await generateReport({ userId: user.uid, title, rules, content });
      } catch (err: any) {
        await updateReport(reportId, { status: "failed", error: err?.message ?? "Backend unreachable" });
        toast({
          title: "Backend error",
          description: err?.message ?? "Could not reach the FastAPI backend.",
          variant: "destructive",
        });
      }
    } catch (err: any) {
      toast({ title: "Failed to create report", description: err?.message, variant: "destructive" });
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
              <div className="flex items-center justify-between">
                <Label htmlFor="content">Content</Label>
                <span className={`text-xs ${content.length > MAX_CONTENT ? "text-destructive" : "text-muted-foreground"}`}>
                  {content.length.toLocaleString()} / {MAX_CONTENT.toLocaleString()}
                </span>
              </div>
              <Textarea
                id="content"
                required
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
