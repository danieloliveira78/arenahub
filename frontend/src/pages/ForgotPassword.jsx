import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Zap, Loader2, MailCheck, ArrowLeft } from "lucide-react";
import { toast } from "sonner";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/auth/forgot-password", { email, origin_url: window.location.origin });
      setSent(true);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao enviar link");
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
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-8" data-testid="forgot-page">
          {sent ? (
            <div className="text-center" data-testid="forgot-sent">
              <div className="mx-auto mb-4 w-14 h-14 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center">
                <MailCheck className="w-7 h-7 text-emerald-400"/>
              </div>
              <h1 className="text-2xl font-extrabold mb-2">Verifique seu e-mail</h1>
              <p className="text-slate-400 text-sm mb-6">
                Se existe uma conta com <span className="text-slate-200 font-semibold">{email}</span>, enviamos um link para redefinir sua senha. Ele expira em 1 hora.
              </p>
              <Link to="/entrar" className="inline-flex items-center gap-1 text-emerald-400 hover:underline text-sm">
                <ArrowLeft className="w-4 h-4"/> Voltar ao login
              </Link>
            </div>
          ) : (
            <>
              <h1 className="text-2xl font-extrabold mb-2">Esqueci minha senha</h1>
              <p className="text-slate-400 text-sm mb-6">Informe seu e-mail e enviaremos um link para você criar uma nova senha.</p>
              <form onSubmit={submit} className="space-y-4">
                <div>
                  <Label>E-mail</Label>
                  <Input required type="email" data-testid="forgot-email"
                    value={email} onChange={e => setEmail(e.target.value)}
                    className="bg-slate-800 border-slate-700"/>
                </div>
                <Button type="submit" disabled={busy} data-testid="forgot-submit"
                  className="w-full bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold h-11">
                  {busy ? <Loader2 className="w-4 h-4 animate-spin"/> : "Enviar link de recuperação"}
                </Button>
              </form>
              <div className="mt-6 pt-6 border-t border-slate-800 text-center text-sm text-slate-400">
                Lembrou a senha? <Link to="/entrar" className="text-emerald-400 hover:underline">Fazer login</Link>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
