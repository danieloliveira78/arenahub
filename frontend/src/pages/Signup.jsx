import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Zap, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function Signup() {
  const nav = useNavigate();
  const { setUser } = useAuth();
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
    setBusy(true);
    try {
      const { data } = await api.post("/auth/signup", form);
      if (data.session_token) localStorage.setItem("session_token", data.session_token);
      setUser(data.user);
      toast.success("Conta criada! Escolha seu plano.");
      nav("/planos");
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
          <h1 className="text-2xl font-extrabold mb-2">Crie sua conta</h1>
          <p className="text-slate-400 text-sm mb-6">14 dias grátis, sem cartão.</p>
          <form onSubmit={submit} className="space-y-3">
            <div><Label>Nome</Label>
              <Input required data-testid="signup-name" value={form.name} onChange={e=>set("name", e.target.value)} className="bg-slate-800 border-slate-700"/></div>
            <div><Label>E-mail</Label>
              <Input required type="email" data-testid="signup-email" value={form.email} onChange={e=>set("email", e.target.value)} className="bg-slate-800 border-slate-700"/></div>
            <div><Label>Telefone (WhatsApp)</Label>
              <Input data-testid="signup-phone" value={form.phone} onChange={e=>set("phone", e.target.value)} className="bg-slate-800 border-slate-700"/></div>
            <div><Label>Organização / clube</Label>
              <Input required data-testid="signup-org" value={form.organization_name} onChange={e=>set("organization_name", e.target.value)} className="bg-slate-800 border-slate-700"/></div>
            <div><Label>Senha</Label>
              <Input required type="password" data-testid="signup-password" value={form.password} onChange={e=>set("password", e.target.value)} className="bg-slate-800 border-slate-700"/></div>
            <div><Label>Confirme a senha</Label>
              <Input required type="password" data-testid="signup-confirm" value={form.confirm} onChange={e=>set("confirm", e.target.value)} className="bg-slate-800 border-slate-700"/></div>
            <label className="flex items-start gap-2 text-sm text-slate-300 pt-2">
              <Checkbox checked={form.accept_terms} onCheckedChange={v=>set("accept_terms", v)} data-testid="signup-terms" className="mt-0.5"/>
              Aceito os <span className="text-emerald-400">Termos de Uso</span>
            </label>
            <label className="flex items-start gap-2 text-sm text-slate-300">
              <Checkbox checked={form.accept_privacy} onCheckedChange={v=>set("accept_privacy", v)} data-testid="signup-privacy" className="mt-0.5"/>
              Aceito a <span className="text-emerald-400">Política de Privacidade</span>
            </label>
            <Button type="submit" disabled={busy} data-testid="signup-submit"
              className="w-full bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold h-11 mt-2">
              {busy ? <Loader2 className="w-4 h-4 animate-spin"/> : "Criar conta"}
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
