import { useState } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { getApiBaseUrl, setApiBaseUrl } from "@/lib/api";
import { toast } from "@/hooks/use-toast";
import { ArrowLeft } from "lucide-react";

export default function Settings() {
  const navigate = useNavigate();
  const [url, setUrl] = useState(getApiBaseUrl());

  const save = (e: React.FormEvent) => {
    e.preventDefault();
    setApiBaseUrl(url);
    toast({ title: "Saved", description: "Backend URL updated." });
  };

  return (
    <AppShell>
      <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="mb-4">
        <ArrowLeft className="mr-2 h-4 w-4" /> Back
      </Button>
      <h1 className="mb-2 text-2xl font-bold tracking-tight sm:text-3xl">Settings</h1>
      <p className="mb-6 text-sm text-muted-foreground">
        Configure the FastAPI backend URL used for report generation and file downloads.
      </p>
      <Card className="gradient-card border-border/60">
        <CardContent className="p-6">
          <form onSubmit={save} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="api">Backend URL</Label>
              <Input
                id="api"
                type="url"
                required
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://your-backend.example.com"
              />
              <p className="text-xs text-muted-foreground">
                Default: <code>http://localhost:8000</code>. The backend code is included in the project's <code>backend/</code> folder.
              </p>
            </div>
            <Button type="submit" className="gradient-primary text-primary-foreground">Save</Button>
          </form>
        </CardContent>
      </Card>
    </AppShell>
  );
}
