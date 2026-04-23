import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import AppShell from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import StatusBadge from "@/components/StatusBadge";
import { Report, RuleViolation, StructuredIssue, subscribeReport } from "@/lib/reports";
import { fileUrl } from "@/lib/api";
import { AlertTriangle, ArrowLeft, Download, FileText, FileType2, Gauge, History, Lightbulb, ShieldAlert } from "lucide-react";

function severityVariant(severity?: string): "default" | "secondary" | "outline" | "destructive" {
  const normalized = (severity || "").toLowerCase();
  if (normalized === "error" || normalized === "critical") return "destructive";
  if (normalized === "warning") return "secondary";
  if (normalized === "info") return "outline";
  return "default";
}

function normalizeIssue(issue: string | StructuredIssue): { message: string; severity?: string; section?: string } {
  if (typeof issue === "string") {
    return { message: issue };
  }
  return {
    message: issue.message || issue.code || "Validation issue",
    severity: issue.severity,
    section: issue.section,
  };
}

function scoreDeltaClass(prev: number | undefined, current: number): string {
  if (prev === undefined) return "bg-primary";
  if (current > prev) return "bg-emerald-500";
  if (current < prev) return "bg-destructive";
  return "bg-amber-500";
}

function formatMetadataLabel(key: string): string {
  const cleaned = String(key || "").replace(/[_-]+/g, " ").trim();
  if (!cleaned) {
    return "Metadata";
  }
  return cleaned
    .split(/\s+/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

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
  const componentScores =
    report.componentScores || report.renderValidation?.componentScores || report.validation?.componentScores;
  const structuredIssues = (report.structuredFeedback?.issues || report.renderValidation?.issues || []).map(normalizeIssue);
  const suggestions = report.structuredFeedback?.suggestions || report.renderValidation?.suggestions || [];
  const ruleViolations: RuleViolation[] =
    report.ruleCompliance?.violations || report.renderValidation?.ruleCompliance?.violations || [];
  const scoreProgression = report.validationScoreProgression || [];
  const correctionHistory = report.correctionHistory || [];

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
          {report.rulesId ? (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="border-emerald-500/40 bg-emerald-500/10 text-emerald-700">
                Extracted rules active
              </Badge>
              <span className="text-xs text-muted-foreground">rules_id: {report.rulesId}</span>
            </div>
          ) : (
            <div className="mt-2">
              <Badge variant="secondary" className="text-xs">Using default/typed rules only</Badge>
            </div>
          )}
          {report.metadata && Object.entries(report.metadata).some(([, value]) => String(value || "").trim()) && (
            <div className="mt-3 text-xs text-muted-foreground space-y-1">
              {Object.entries(report.metadata)
                .filter(([, value]) => String(value || "").trim())
                .map(([key, value]) => (
                  <div key={key}>
                    <strong>{formatMetadataLabel(key)}:</strong> {value}
                  </div>
                ))}
            </div>
          )}
          {report.sections && report.sections.length > 0 && (
            <div className="mt-3 text-xs text-muted-foreground">
              <div className="font-medium mb-1">Sections ({report.sections.length}):</div>
              <ul className="list-disc pl-4 space-y-0.5">
                {report.sections.map((section, idx) => (
                  <li key={idx}>
                    {section.title} {section.mode === "auto_generate" && <span className="text-emerald-600">[AI]</span>}
                    {section.mode === "user_provides" && <span className="text-blue-600">[User]</span>}
                    {section.mode === "skip" && <span className="text-gray-400">[Skip]</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {report.ruleOverrides && Object.keys(report.ruleOverrides).length > 0 && (
            <div className="mt-3 text-xs text-muted-foreground">
              <div className="font-medium mb-1">Rule Overrides:</div>
              <ul className="list-disc pl-4 space-y-0.5">
                {Object.entries(report.ruleOverrides).map(([key, value]) => (
                  <li key={key}>{key}: {value}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <StatusBadge status={report.status} />
      </div>

      {report.status === "failed" && report.error && (
        <Card className="mb-6 border-destructive/40 bg-destructive/10">
          <CardContent className="p-4 text-sm text-destructive">
            <strong>Generation failed:</strong> {report.error}
            {report.qualityFailure && (report.qualityErrors?.length || 0) > 0 && (
              <ul className="mt-2 list-disc pl-5 text-xs">
                {report.qualityErrors?.map((item, idx) => (
                  <li key={`${idx}-${item}`}>{item}</li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      )}

      {(report.status === "pending" || report.status === "processing") && (
        <Card className="mb-6 border-info/30 bg-info/10">
          <CardContent className="p-4 text-sm text-info">
            <strong>Status:</strong> {report.status === "pending" ? "Queued" : "Processing"}
            {report.inputProcessing && (
              <div className="mt-1 text-xs text-muted-foreground">
                Files processed: {report.inputProcessing.processed ?? 0}, failed: {report.inputProcessing.failed ?? 0}
              </div>
            )}
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
        {report.validation && (
          <Card className="gradient-card border-border/60">
            <CardContent className="p-5">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Quality Checks</h3>
              <p className="text-sm text-muted-foreground">
                Score: {report.validation.qualityScore ?? "-"} | Retried: {report.validation.retried ? "yes" : "no"}
              </p>
            </CardContent>
          </Card>
        )}
        {componentScores && (
          <Card className="gradient-card border-border/60">
            <CardContent className="p-5">
              <div className="mb-3 flex items-center gap-2">
                <Gauge className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Component Scores</h3>
              </div>
              <div className="grid gap-2 text-sm sm:grid-cols-3">
                <div className="rounded-md border border-border/60 bg-background/30 p-3">
                  <div className="text-xs text-muted-foreground">Structure</div>
                  <div className="text-lg font-semibold">{componentScores.structureScore ?? "-"}</div>
                </div>
                <div className="rounded-md border border-border/60 bg-background/30 p-3">
                  <div className="text-xs text-muted-foreground">Formatting</div>
                  <div className="text-lg font-semibold">{componentScores.formattingScore ?? "-"}</div>
                </div>
                <div className="rounded-md border border-border/60 bg-background/30 p-3">
                  <div className="text-xs text-muted-foreground">Rule Compliance</div>
                  <div className="text-lg font-semibold">{componentScores.ruleComplianceScore ?? "-"}</div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
        {(structuredIssues.length > 0 || suggestions.length > 0) && (
          <Card className="gradient-card border-border/60">
            <CardContent className="space-y-4 p-5">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Structured Feedback</h3>
              </div>

              {structuredIssues.length > 0 && (
                <div>
                  <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Issues</p>
                  <div className="space-y-2">
                    {structuredIssues.map((issue, idx) => (
                      <div key={`issue-${idx}-${issue.message}`} className="rounded-md border border-border/60 p-3 text-sm">
                        <div className="flex items-start justify-between gap-2">
                          <span>{issue.message}</span>
                          {issue.severity && <Badge variant={severityVariant(issue.severity)}>{issue.severity}</Badge>}
                        </div>
                        {issue.section && <p className="mt-1 text-xs text-muted-foreground">Section: {issue.section}</p>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {suggestions.length > 0 && (
                <div>
                  <p className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    <Lightbulb className="h-3.5 w-3.5" />
                    Suggestions
                  </p>
                  <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                    {suggestions.map((suggestion, idx) => (
                      <li key={`suggestion-${idx}-${suggestion}`}>{suggestion}</li>
                    ))}
                  </ul>
                </div>
              )}
            </CardContent>
          </Card>
        )}
        {ruleViolations.length > 0 && (
          <Card className="gradient-card border-border/60">
            <CardContent className="space-y-3 p-5">
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Rule Compliance</h3>
              </div>
              <div className="space-y-2">
                {ruleViolations.map((violation, idx) => (
                  <div key={`violation-${idx}-${violation.message || violation.rule || idx}`} className="rounded-md border border-border/60 p-3 text-sm">
                    <div className="flex items-start justify-between gap-2">
                      <span>{violation.message || violation.rule || "Rule violation"}</span>
                      <div className="flex items-center gap-2">
                        {typeof violation.penalty === "number" && (
                          <Badge variant="outline">-{violation.penalty} pts</Badge>
                        )}
                        {violation.severity && <Badge variant={severityVariant(violation.severity)}>{violation.severity}</Badge>}
                      </div>
                    </div>
                    {violation.rule && <p className="mt-1 text-xs text-muted-foreground">Rule: {violation.rule}</p>}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
        {(correctionHistory.length > 0 || scoreProgression.length > 0 || report.correctionBackoffTriggered) && (
          <Card className="gradient-card border-border/60">
            <CardContent className="space-y-3 p-5">
              <div className="flex items-center gap-2">
                <History className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Correction Timeline</h3>
              </div>
              {scoreProgression.length > 0 && (
                <div className="space-y-2">
                  <p className="text-sm text-muted-foreground">Score progression: {scoreProgression.join(" -> ")}</p>
                  <div className="rounded-md border border-border/60 bg-background/30 p-3">
                    <div className="mb-2 grid grid-cols-6 gap-2 sm:grid-cols-8 md:grid-cols-10">
                      {scoreProgression.map((score, idx) => {
                        const prev = idx > 0 ? scoreProgression[idx - 1] : undefined;
                        return (
                          <div key={`score-step-${idx}-${score}`} className="space-y-1 text-center">
                            <div
                              className={`mx-auto h-10 w-3 rounded-full ${scoreDeltaClass(prev, score)}`}
                              style={{ opacity: Math.max(0.35, Math.min(1, score / 100)) }}
                              title={`Attempt ${idx + 1}: ${score}`}
                            />
                            <div className="text-[10px] text-muted-foreground">{idx + 1}</div>
                          </div>
                        );
                      })}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Green: improved, amber: unchanged, red: regressed.
                    </p>
                  </div>
                </div>
              )}
              {correctionHistory.length > 0 && (
                <div className="space-y-2">
                  {correctionHistory.map((attempt, idx) => (
                    <div key={`attempt-${idx}-${attempt.attempt || idx}`} className="rounded-md border border-border/60 p-3 text-sm">
                      <div className="font-medium">Attempt {attempt.attempt ?? idx + 1}</div>
                      <p className="text-xs text-muted-foreground">
                        Strategy: {attempt.strategy || "-"} | Score: {attempt.score ?? "-"}
                      </p>
                      {attempt.reason && <p className="mt-1 text-xs text-muted-foreground">Reason: {attempt.reason}</p>}
                    </div>
                  ))}
                </div>
              )}
              {report.correctionBackoffTriggered && (
                <p className="text-xs text-amber-600 dark:text-amber-400">Backoff triggered: retries stopped due to low expected improvement.</p>
              )}
            </CardContent>
          </Card>
        )}
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
