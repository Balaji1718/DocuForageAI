import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import AppShell from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import StatusBadge from "@/components/StatusBadge";
import { listReports, Report } from "@/lib/reports";
import { FileText, Plus, RefreshCw } from "lucide-react";

function reportSecondaryState(report: Report): string {
  if (report.status === "processing" && report.correctionBackoffTriggered) {
    return "Correction retries stopped (backoff triggered)";
  }
  if (report.qualityFailure) {
    return "Quality validation failed";
  }
  const score = report.validation?.qualityScore ?? report.renderValidation?.score;
  if (typeof score === "number") {
    return `Quality score: ${score}`;
  }
  return "";
}

export default function Dashboard() {
  const { user } = useAuth();
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      const list = await listReports(user.uid);
      setReports(list);
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    refresh();
    // Polling for status updates
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  return (
    <AppShell>
      <section className="mb-8 rounded-2xl border border-border/60 gradient-card p-6 shadow-card sm:p-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Your Reports</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Welcome back, {user?.email}. Generate structured PDF & DOCX reports from your rules and content.
            </p>
          </div>
          <Link to="/reports/new">
            <Button className="gradient-primary text-primary-foreground hover:opacity-90">
              <Plus className="mr-2 h-4 w-4" /> New Report
            </Button>
          </Link>
        </div>
      </section>

      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium uppercase tracking-wider text-muted-foreground">
          {reports.length} report{reports.length === 1 ? "" : "s"}
        </h2>
        <Button variant="ghost" size="sm" onClick={refresh} disabled={loading}>
          <RefreshCw className={`mr-2 h-3 w-3 ${loading ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>

      {loading && reports.length === 0 ? (
        <div className="grid gap-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-xl bg-secondary/50" />
          ))}
        </div>
      ) : reports.length === 0 ? (
        <Card className="border-dashed border-border/60 bg-transparent">
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-secondary">
              <FileText className="h-6 w-6 text-muted-foreground" />
            </div>
            <h3 className="font-semibold">No reports yet</h3>
            <p className="mt-1 text-sm text-muted-foreground">Create your first AI-generated report.</p>
            <Link to="/reports/new" className="mt-4">
              <Button className="gradient-primary text-primary-foreground">
                <Plus className="mr-2 h-4 w-4" /> Create Report
              </Button>
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3">
          {reports.map((r) => (
            <Link key={r.id} to={`/reports/${r.id}`}>
              <Card className="transition hover:border-primary/40 hover:shadow-glow gradient-card border-border/60">
                <CardContent className="flex items-center justify-between gap-4 p-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="truncate font-semibold">{r.title || "Untitled report"}</h3>
                    </div>
                    <p className="mt-1 truncate text-xs text-muted-foreground">
                      {r.createdAt?.toDate?.().toLocaleString?.() ?? "Just now"}
                    </p>
                    {reportSecondaryState(r) && (
                      <p className="mt-1 truncate text-xs text-amber-400">{reportSecondaryState(r)}</p>
                    )}
                  </div>
                  <StatusBadge status={r.status} />
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </AppShell>
  );
}
