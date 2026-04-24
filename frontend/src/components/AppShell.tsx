import { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { FileText, LogOut, UserRound } from "lucide-react";
import ThemeToggle from "@/components/ThemeToggle";

export default function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4">
          <Link to="/" className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg gradient-primary shadow-glow">
              <FileText className="h-5 w-5 text-primary-foreground" />
            </div>
            <div className="leading-tight">
              <div className="font-semibold tracking-tight">DocuForge <span className="text-gradient">AI</span></div>
              <div className="text-[10px] uppercase tracking-widest text-muted-foreground">Precision Documents</div>
            </div>
          </Link>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Button variant="ghost" size="icon" onClick={() => navigate("/settings")} aria-label="Profile">
              <UserRound className="h-4 w-4" />
            </Button>
            {user && (
              <Button variant="ghost" size="sm" onClick={() => logout()}>
                <LogOut className="mr-2 h-4 w-4" /> Logout
              </Button>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6 sm:py-10">{children}</main>
    </div>
  );
}
