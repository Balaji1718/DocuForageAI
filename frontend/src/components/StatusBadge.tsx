import { Badge } from "@/components/ui/badge";
import { ReportStatus } from "@/lib/reports";
import { CheckCircle2, Clock, Loader2, XCircle } from "lucide-react";

const styles: Record<ReportStatus, string> = {
  pending: "bg-warning/15 text-warning border-warning/30",
  processing: "bg-info/15 text-info border-info/30",
  completed: "bg-success/15 text-success border-success/30",
  failed: "bg-destructive/15 text-destructive border-destructive/30",
};

const icons: Record<ReportStatus, JSX.Element> = {
  pending: <Clock className="h-3 w-3" />,
  processing: <Loader2 className="h-3 w-3 animate-spin" />,
  completed: <CheckCircle2 className="h-3 w-3" />,
  failed: <XCircle className="h-3 w-3" />,
};

export default function StatusBadge({ status }: { status: ReportStatus }) {
  return (
    <Badge variant="outline" className={`gap-1 capitalize ${styles[status]}`}>
      {icons[status]}
      {status}
    </Badge>
  );
}
