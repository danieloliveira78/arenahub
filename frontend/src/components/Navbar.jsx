import { Link, useLocation } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Zap, User, LogOut, LayoutDashboard, Shield } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const Navbar = () => {
  const { user, login, logout } = useAuth();
  const location = useLocation();
  const [tenantInfo, setTenantInfo] = useState(null);

  useEffect(() => {
    if (!user || user.account_type === "athlete") { setTenantInfo(null); return; }
    api.get("/me/tenant").then(({data}) => setTenantInfo(data)).catch(()=>{});
  }, [user]);

  const nav = [
    { to: "/competicoes", label: "Torneios" },
    { to: "/ranking", label: "Ranking" },
  ];

  const trialBanner = (() => {
    if (!tenantInfo) return null;
    const t = tenantInfo.tenant || {};
    const st = tenantInfo.effective_status;
    if (st === "trialing" && t.trial_end) {
      const days = Math.max(0, Math.ceil((new Date(t.trial_end) - new Date())/86400000));
      return { text: `Trial ativo · ${days} dia${days===1?"":"s"} restantes`, cls: "bg-cyan-500/15 border-cyan-500/40 text-cyan-200" };
    }
    if (st === "grace_period") return { text: "Pagamento pendente · edição bloqueada em breve", cls: "bg-amber-500/15 border-amber-500/40 text-amber-200" };
    if (st === "inactive") return { text: "Assinatura inativa · edição bloqueada", cls: "bg-red-500/15 border-red-500/40 text-red-200" };
    return null;
  })();

  return (
    <nav className="sticky top-0 z-50 backdrop-blur-xl bg-[#0B0F17]/80 border-b border-white/5" data-testid="navbar">
      {trialBanner && (
        <div className={`w-full text-center text-xs py-1.5 border-b ${trialBanner.cls}`} data-testid="trial-banner">
          {trialBanner.text} · <Link to="/planos" className="underline font-semibold">ver planos</Link>
        </div>
      )}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <Link to="/" className="flex items-center gap-2 group" data-testid="navbar-logo">
            <div className="w-9 h-9 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center group-hover:bg-emerald-500/20 transition-colors">
              <Zap className="w-5 h-5 text-emerald-400" strokeWidth={2.5} />
            </div>
            <span className="font-extrabold text-xl tracking-tight text-white">Arena<span className="text-emerald-400">Hub</span></span>
          </Link>

          <div className="hidden md:flex items-center gap-1">
            {nav.map((n) => (
              <Link key={n.to} to={n.to} data-testid={`nav-${n.label.toLowerCase()}`}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  location.pathname === n.to ? "text-emerald-400 bg-emerald-500/10" : "text-slate-300 hover:text-white hover:bg-white/5"
                }`}>{n.label}</Link>
            ))}
            {user?.is_admin && (
              <Link to="/admin" data-testid="nav-admin"
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-1.5 ${
                  location.pathname.startsWith("/admin") ? "text-amber-400 bg-amber-500/10" : "text-slate-300 hover:text-white hover:bg-white/5"
                }`}>
                <Shield className="w-4 h-4" /> Admin
              </Link>
            )}
          </div>

          <div className="flex items-center gap-3">
            {!user ? (
              <>
                <Link to="/entrar" className="hidden sm:inline text-sm text-slate-300 hover:text-white">Entrar</Link>
                <Link to="/cadastro">
                  <Button data-testid="signup-btn"
                    className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold rounded-full px-5">
                    Começar grátis
                  </Button>
                </Link>
              </>
            ) : (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button className="flex items-center gap-2 rounded-full pl-1 pr-3 py-1 border border-white/10 hover:bg-white/5" data-testid="user-menu-btn">
                    <Avatar className="w-8 h-8">
                      <AvatarImage src={user.picture} />
                      <AvatarFallback className="bg-emerald-500/20 text-emerald-300 text-xs">{user.name?.[0]}</AvatarFallback>
                    </Avatar>
                    <span className="hidden sm:inline text-sm text-slate-200 font-medium">{user.name?.split(" ")[0]}</span>
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="bg-slate-900 border-slate-800 text-slate-100 w-56">
                  <DropdownMenuLabel className="text-slate-400 text-xs">{user.email}</DropdownMenuLabel>
                  <DropdownMenuSeparator className="bg-slate-800" />
                  <DropdownMenuItem asChild>
                    <Link to="/dashboard" data-testid="menu-dashboard" className="flex items-center gap-2 cursor-pointer">
                      <LayoutDashboard className="w-4 h-4" /> Meu Painel
                    </Link>
                  </DropdownMenuItem>
                  {user.is_admin && (
                    <DropdownMenuItem asChild>
                      <Link to="/admin" data-testid="menu-admin" className="flex items-center gap-2 cursor-pointer">
                        <Shield className="w-4 h-4 text-amber-400" /> Painel Admin
                      </Link>
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuItem asChild>
                    <Link to="/minha-assinatura" data-testid="menu-subscription" className="flex items-center gap-2 cursor-pointer">
                      <Shield className="w-4 h-4 text-emerald-400" /> Minha Assinatura
                    </Link>
                  </DropdownMenuItem>
                  {user.platform_role === "super_admin" && (
                    <DropdownMenuItem asChild>
                      <Link to="/platform/admin" data-testid="menu-platform" className="flex items-center gap-2 cursor-pointer">
                        <Shield className="w-4 h-4 text-purple-400" /> Painel da Plataforma
                      </Link>
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuSeparator className="bg-slate-800" />
                  <DropdownMenuItem onClick={logout} data-testid="menu-logout" className="cursor-pointer text-red-300 focus:text-red-200">
                    <LogOut className="w-4 h-4 mr-2" /> Sair
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
};

export default Navbar;
