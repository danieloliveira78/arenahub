import { useState, useEffect } from "react";
import { Link, useSearchParams, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Zap, Loader2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const nav = useNavigate();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!token) toast.error("Link inválido: token ausente");
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    if (password !== confirm) { toast.error("Senhas não coincidem"); return; }
    if (password.length < 6) { toast.error("Mínimo 6 caracteres"); return; }
    setBusy(true);
    try {
      await api.post("/auth/reset-password", { token, new_password: password });
      setDone(true);
      setTimeout(() => nav("/entrar"), 2500);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao redefinir senha");
    } finally {
      setBusy(false);
    }
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
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-8" data-testid="reset-page">
          {done ? (
            <div className="text-center" data-testid="reset-done">
              <div className="mx-auto mb-4 w-14 h-14 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center">
                <ShieldCheck className="w-7 h-7 text-emerald-400"/>
              </div>
              <h1 className="text-2xl font-extrabold mb-2">Senha redefinida!</h1>
              <p className="text-slate-400 text-sm mb-6">Você já pode entrar com a nova senha. Redirecionando...</p>
              <Link to="/entrar" className="text-emerald-400 hover:underline text-sm">Ir para o login</Link>
            </div>
          ) : (
            <>
              <h1 className="text-2xl font-extrabold mb-2">Criar nova senha</h1>
              <p className="text-slate-400 text-sm mb-6">Escolha uma senha segura. Mínimo 6 caracteres.</p>
              <form onSubmit={submit} className="space-y-4">
                <div>
                  <Label>Nova senha</Label>
                  <Input required type="password" data-testid="reset-password"
                    value={password} onChange={e => setPassword(e.target.value)}
                    className="bg-slate-800 border-slate-700"/>
                </div>
                <div>
                  <Label>Confirmar nova senha</Label>
                  <Input required type="password" data-testid="reset-confirm"
                    value={confirm} onChange={e => setConfirm(e.target.value)}
                    className="bg-slate-800 border-slate-700"/>
                </div>
                <Button type="submit" disabled={busy || !token} data-testid="reset-submit"
                  className="w-full bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold h-11">
                  {busy ? <Loader2 className="w-4 h-4 animate-spin"/> : "Redefinir senha"}
                </Button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
