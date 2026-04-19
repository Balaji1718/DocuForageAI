import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import AppShell from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import StatusBadge from "@/components/StatusBadge";
import { Report, subscribeReport } from "@/lib/reports";
import { fileUrl } from "@/lib/api";
import { ArrowLeft, Download, FileText, FileType2 } from "lucide-react";

export default function ReportDetail() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    const unsub = subscribeReport(id, (r) => {
      setReport(r);
      setLoading(false);
    });
    return unsub;
  }, [id]);

  if (loading) {
    return (
      <AppShell>
        <div className="h-40 animate-pulse rounded-xl bg-secondary/50" />
      </AppShell>
    );
  }

  if (!report) {
    return (
      <AppShell>
        <div className="text-center text-muted-foreground">Report not found.</div>
      </AppShell>
    );
  }

  const pdf = fileUrl(report.pdfUrl || "");
  const docx = fileUrl(report.docxUrl || "");

  return (
    <AppShell>
      <Button variant="ghost" size="sm" onClick={() => navigate("/")} className="mb-4">
        <ArrowLeft className="mr-2 h-4 w-4" /> Back to dashboard
      </Button>

      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{report.title}</h1>
          <p className="mt-1 text-xs text-muted-foreground">
            Created {report.createdAt?.toDate?.().toLocaleString?.() ?? "—"}
          </p>
        </div>
        <StatusBadge status={report.status} />
      </div>

      {report.status === "failed" && report.error && (
        <Card className="mb-6 border-destructive/40 bg-destructive/10">
          <CardContent className="p-4 text-sm text-destructive">
            <strong>Generation failed:</strong> {report.error}
          </CardContent>
        </Card>
      )}

      {report.status === "completed" && (
        <div className="mb-6 grid gap-3 sm:grid-cols-2">
          <a href={pdf} target="_blank" rel="noreferrer" download>
            <Card className="transition hover:border-primary/40 hover:shadow-glow gradient-card border-border/60">
              <CardContent className="flex items-center gap-4 p-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-lg gradient-primary shadow-glow">
                  <FileType2 className="h-6 w-6 text-primary-foreground" />
                </div>
                <div className="flex-1">
                  <div className="font-semibold">Download PDF</div>
                  <div className="text-xs text-muted-foreground truncate">{report.pdfUrl}</div>
                </div>
                <Download className="h-4 w-4 text-muted-foreground" />
              </CardContent>
            </Card>
          </a>
          <a href={docx} target="_blank" rel="noreferrer" download>
            <Card className="transition hover:border-primary/40 hover:shadow-glow gradient-card border-border/60">
              <CardContent className="flex items-center gap-4 p-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-accent">
                  <FileText className="h-6 w-6 text-accent-foreground" />
                </div>
                <div className="flex-1">
                  <div className="font-semibold">Download DOCX</div>
                  <div className="text-xs text-muted-foreground truncate">{report.docxUrl}</div>
                </div>
                <Download className="h-4 w-4 text-muted-foreground" />
              </CardContent>
            </Card>
          </a>
        </div>
      )}

      <div className="grid gap-4">
        <Card className="gradient-card border-border/60">
          <CardContent className="p-5">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Formatting Rules</h3>
            <p className="whitespace-pre-wrap text-sm">{report.rules}</p>
          </CardContent>
        </Card>
        <Card className="gradient-card border-border/60">
          <CardContent className="p-5">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Content</h3>
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap font-mono text-xs text-muted-foreground">
              {report.content}
            </pre>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
