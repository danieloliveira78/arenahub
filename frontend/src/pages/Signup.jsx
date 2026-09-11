import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Zap, Loader2, Trophy, Building2 } from "lucide-react";
import { toast } from "sonner";

export default function Signup() {
  const nav = useNavigate();
  const { setUser } = useAuth();
  const [accountType, setAccountType] = useState("admin"); // "admin" | "athlete"
  const [form, setForm] = useState({
    name: "", email: "", phone: "", password: "", confirm: "",
    organization_name: "", accept_terms: false, accept_privacy: false,
  });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    if (form.password !== form.confirm) { toast.error("Senhas não coincidem"); return; }
    if (!form.accept_terms || !form.accept_privacy) { toast.error("Aceite os termos e a política"); return; }
    if (accountType === "admin" && !form.organization_name.trim()) {
      toast.error("Informe o nome da sua organização"); return;
    }
    setBusy(true);
    try {
      const { data } = await api.post("/auth/signup", { ...form, account_type: accountType });
      if (data.session_token) localStorage.setItem("session_token", data.session_token);
      setUser(data.user);
      if (accountType === "athlete") {
        toast.success("Conta criada! Explore os torneios abertos.");
        nav("/competicoes");
      } else {
        toast.success("Conta criada! Escolha seu plano.");
        nav("/planos");
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro no cadastro");
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4 py-10">
      <div className="max-w-md w-full">
        <Link to="/" className="flex items-center gap-2 mb-8 justify-center">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center">
            <Zap className="w-5 h-5 text-emerald-400" strokeWidth={2.5}/>
          </div>
          <span className="font-extrabold text-2xl">Arena<span className="text-emerald-400">Hub</span></span>
        </Link>
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-8">
          <h1 className="text-2xl font-extrabold mb-2">Criar conta</h1>
          <p className="text-sm text-slate-400 mb-4">Escolha o tipo de conta que quer criar.</p>

          <div className="grid grid-cols-2 gap-2 mb-6" role="tablist" aria-label="Tipo de conta">
            <button type="button" onClick={() => setAccountType("athlete")}
              data-testid="account-type-athlete"
              className={`p-3 rounded-xl border-2 text-left transition-colors ${
                accountType === "athlete" ? "border-emerald-500 bg-emerald-500/10"
                                          : "border-slate-800 hover:border-slate-700"}`}>
              <Trophy className="w-5 h-5 text-emerald-400 mb-1"/>
              <div className="font-bold text-sm">Sou atleta</div>
              <div className="text-[11px] text-slate-400">Participar de torneios</div>
            </button>
            <button type="button" onClick={() => setAccountType("admin")}
              data-testid="account-type-admin"
              className={`p-3 rounded-xl border-2 text-left transition-colors ${
                accountType === "admin" ? "border-emerald-500 bg-emerald-500/10"
                                        : "border-slate-800 hover:border-slate-700"}`}>
              <Building2 className="w-5 h-5 text-amber-400 mb-1"/>
              <div className="font-bold text-sm">Sou organizador</div>
              <div className="text-[11px] text-slate-400">Gerenciar minha arena</div>
            </button>
          </div>

          <form onSubmit={submit} className="space-y-3">
            <div><Label>Nome completo</Label>
              <Input required data-testid="signup-name" value={form.name}
                onChange={e=>set("name", e.target.value)} className="bg-slate-800 border-slate-700"/></div>
            <div><Label>E-mail</Label>
              <Input required type="email" data-testid="signup-email" value={form.email}
                onChange={e=>set("email", e.target.value)} className="bg-slate-800 border-slate-700"/></div>
            <div><Label>Telefone (WhatsApp)</Label>
              <Input data-testid="signup-phone" value={form.phone}
                onChange={e=>set("phone", e.target.value)} className="bg-slate-800 border-slate-700"/></div>
            {accountType === "admin" && (
              <div><Label>Nome da organização</Label>
                <Input required data-testid="signup-org" value={form.organization_name}
                  onChange={e=>set("organization_name", e.target.value)}
                  placeholder="Ex: Arena Beach Club"
                  className="bg-slate-800 border-slate-700"/></div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Senha</Label>
                <Input required type="password" data-testid="signup-password" value={form.password}
                  onChange={e=>set("password", e.target.value)} className="bg-slate-800 border-slate-700"/></div>
              <div><Label>Confirmar</Label>
                <Input required type="password" data-testid="signup-confirm" value={form.confirm}
                  onChange={e=>set("confirm", e.target.value)} className="bg-slate-800 border-slate-700"/></div>
            </div>
            <label className="flex items-start gap-2 text-xs text-slate-400 pt-2 cursor-pointer">
              <Checkbox data-testid="signup-terms" checked={form.accept_terms}
                onCheckedChange={v=>set("accept_terms", !!v)} className="mt-0.5"/>
              Aceito os <a href="#" className="text-emerald-400">termos de uso</a>.
            </label>
            <label className="flex items-start gap-2 text-xs text-slate-400 cursor-pointer">
              <Checkbox data-testid="signup-privacy" checked={form.accept_privacy}
                onCheckedChange={v=>set("accept_privacy", !!v)} className="mt-0.5"/>
              Aceito a <a href="#" className="text-emerald-400">política de privacidade</a>.
            </label>
            <Button type="submit" disabled={busy} data-testid="signup-submit"
              className="w-full bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold h-11 mt-2">
              {busy ? <Loader2 className="w-4 h-4 animate-spin"/> :
                (accountType === "athlete" ? "Criar conta de atleta" : "Criar conta e escolher plano")}
            </Button>
          </form>
          <div className="mt-6 pt-6 border-t border-slate-800 text-center text-sm text-slate-400">
            Já tem conta? <Link to="/entrar" className="text-emerald-400 hover:underline">Entrar</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
