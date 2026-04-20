import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useAuth } from "@/contexts/AuthContext";
import { getApiBaseUrl } from "@/lib/api";
import { ArrowLeft, UserRound, Mail, ShieldCheck, Fingerprint, CalendarDays } from "lucide-react";

export default function Settings() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const displayName = user?.displayName || user?.email?.split("@")[0] || "Profile";
  const email = user?.email || "No email available";
  const provider = user?.providerData?.[0]?.providerId || "firebase";
  const createdAt = useMemo(() => {
    const value = user?.metadata?.creationTime;
    return value ? new Date(value).toLocaleString() : "Unknown";
  }, [user?.metadata?.creationTime]);
  const lastLogin = useMemo(() => {
    const value = user?.metadata?.lastSignInTime;
    return value ? new Date(value).toLocaleString() : "Unknown";
  }, [user?.metadata?.lastSignInTime]);
  const apiBaseUrl = useMemo(() => getApiBaseUrl(), []);

  return (
    <AppShell>
      <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="mb-4">
        <ArrowLeft className="mr-2 h-4 w-4" /> Back
      </Button>
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl gradient-primary shadow-glow">
          <UserRound className="h-6 w-6 text-primary-foreground" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Profile</h1>
          <p className="text-sm text-muted-foreground">View the signed-in account that powers your reports and downloads.</p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="gradient-card border-border/60">
          <CardContent className="space-y-4 p-6">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/15 text-primary">
                <UserRound className="h-5 w-5" />
              </div>
              <div>
                <div className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Account</div>
                <div className="text-lg font-semibold">{displayName}</div>
              </div>
            </div>

            <div className="grid gap-3 text-sm">
              <div className="flex items-start gap-3 rounded-lg border border-border/60 bg-background/30 p-3">
                <Mail className="mt-0.5 h-4 w-4 text-muted-foreground" />
                <div>
                  <div className="text-xs uppercase tracking-wide text-muted-foreground">Email</div>
                  <div className="font-medium">{email}</div>
                </div>
              </div>
              <div className="flex items-start gap-3 rounded-lg border border-border/60 bg-background/30 p-3">
                <ShieldCheck className="mt-0.5 h-4 w-4 text-muted-foreground" />
                <div>
                  <div className="text-xs uppercase tracking-wide text-muted-foreground">Provider</div>
                  <div className="font-medium">{provider}</div>
                </div>
              </div>
              <div className="flex items-start gap-3 rounded-lg border border-border/60 bg-background/30 p-3">
                <Fingerprint className="mt-0.5 h-4 w-4 text-muted-foreground" />
                <div>
                  <div className="text-xs uppercase tracking-wide text-muted-foreground">User ID</div>
                  <div className="break-all font-mono text-xs font-medium">{user?.uid || "Unknown"}</div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="gradient-card border-border/60">
          <CardContent className="space-y-4 p-6">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent/15 text-accent-foreground">
                <CalendarDays className="h-5 w-5" />
              </div>
              <div>
                <div className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Activity</div>
                <div className="text-lg font-semibold">Session details</div>
              </div>
            </div>

            <div className="grid gap-3 text-sm">
              <div className="rounded-lg border border-border/60 bg-background/30 p-3">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">Account created</div>
                <div className="font-medium">{createdAt}</div>
              </div>
              <div className="rounded-lg border border-border/60 bg-background/30 p-3">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">Last sign-in</div>
                <div className="font-medium">{lastLogin}</div>
              </div>
              <div className="rounded-lg border border-border/60 bg-background/30 p-3 text-muted-foreground">
                This screen now focuses on the profile tied to your Firebase session instead of backend connection settings.
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="mt-4 gradient-card border-border/60">
        <CardContent className="space-y-2 p-6">
          <div className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Connection</div>
          <p className="text-sm text-muted-foreground">Active backend endpoint</p>
          <div className="rounded-lg border border-border/60 bg-background/30 p-3 font-mono text-xs break-all">
            {apiBaseUrl}
          </div>
        </CardContent>
      </Card>
    </AppShell>
  );
}
