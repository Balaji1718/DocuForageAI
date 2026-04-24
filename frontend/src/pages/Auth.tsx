import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "@/hooks/use-toast";
import { FileText, Sparkles } from "lucide-react";
import ThemeToggle from "@/components/ThemeToggle";

export default function Auth() {
  const { signIn, signUp } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (mode === "login") await signIn(email, password);
      else await signUp(email, password);
      navigate("/");
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : "Please try again.";
      toast({
        title: mode === "login" ? "Login failed" : "Signup failed",
        description: errorMessage,
        variant: "destructive",
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-background">
      <div className="absolute right-4 top-4 z-20">
        <ThemeToggle />
      </div>

      <div className="absolute inset-0 -z-10 opacity-30">
        <div className="absolute -left-24 top-10 h-72 w-72 rounded-full bg-primary blur-3xl" />
        <div className="absolute right-0 top-1/2 h-80 w-80 rounded-full bg-accent blur-3xl" />
      </div>

      <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4 py-12">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl gradient-primary shadow-glow">
            <FileText className="h-7 w-7 text-primary-foreground" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight">
            DocuForge <span className="text-gradient">AI</span>
          </h1>
          <p className="mt-2 flex items-center justify-center gap-1 text-sm text-muted-foreground">
            <Sparkles className="h-3 w-3" /> Precision Document Generation, Powered by AI
          </p>
        </div>

        <Card className="border-border/60 shadow-card gradient-card">
          <CardContent className="p-6">
            <div className="mb-6 grid grid-cols-2 rounded-lg bg-secondary p-1">
              <button
                onClick={() => setMode("login")}
                className={`rounded-md py-2 text-sm font-medium transition ${
                  mode === "login" ? "bg-background text-foreground shadow" : "text-muted-foreground"
                }`}
              >
                Login
              </button>
              <button
                onClick={() => setMode("signup")}
                className={`rounded-md py-2 text-sm font-medium transition ${
                  mode === "signup" ? "bg-background text-foreground shadow" : "text-muted-foreground"
                }`}
              >
                Sign up
              </button>
            </div>

            <form onSubmit={submit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  required
                  minLength={6}
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                />
              </div>
              <Button type="submit" disabled={busy} className="w-full gradient-primary text-primary-foreground hover:opacity-90">
                {busy ? "Please wait…" : mode === "login" ? "Login" : "Create account"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <p className="mt-6 text-center text-xs text-muted-foreground">
          By continuing you agree to the DocuForge AI terms.
        </p>
      </div>
    </div>
  );
}
