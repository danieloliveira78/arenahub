import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Zap, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function Login() {
  const nav = useNavigate();
  const { setUser, login: googleLogin } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/auth/login", { email, password });
      if (data.session_token) localStorage.setItem("session_token", data.session_token);
      setUser(data.user);
      toast.success("Bem-vindo!");
      nav("/dashboard");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro no login");
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
          <h1 className="text-2xl font-extrabold mb-6">Entrar na plataforma</h1>
          <form onSubmit={submit} className="space-y-3">
            <div><Label>E-mail</Label>
              <Input required type="email" data-testid="login-email" value={email} onChange={e=>setEmail(e.target.value)} className="bg-slate-800 border-slate-700"/></div>
            <div><Label>Senha</Label>
              <Input required type="password" data-testid="login-password" value={password} onChange={e=>setPassword(e.target.value)} className="bg-slate-800 border-slate-700"/></div>
            <Button type="submit" disabled={busy} data-testid="login-submit"
              className="w-full bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold h-11 mt-2">
              {busy ? <Loader2 className="w-4 h-4 animate-spin"/> : "Entrar"}
            </Button>
          </form>
          <div className="my-6 flex items-center gap-3 text-xs text-slate-500">
            <div className="flex-1 h-px bg-slate-800"/> OU <div className="flex-1 h-px bg-slate-800"/>
          </div>
          <Button onClick={googleLogin} data-testid="login-google" variant="outline"
            className="w-full border-slate-700 hover:bg-slate-800 h-11">
            Entrar com Google
          </Button>
          <div className="mt-6 pt-6 border-t border-slate-800 text-center text-sm text-slate-400">
            Não tem conta? <Link to="/cadastro" className="text-emerald-400 hover:underline">Criar agora</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
