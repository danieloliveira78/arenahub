import { useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { QrCode, CheckCircle2, XCircle, Loader2, UserCheck } from "lucide-react";
import { toast } from "sonner";

export default function CheckIn() {
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const process = async (raw) => {
    const c = (raw || code).trim();
    if (!c) return;
    setLoading(true); setError(""); setResult(null);
    try {
      const { data } = await api.post(`/checkin/${c}`);
      setResult(data);
      if (data.already) toast.info("Atleta já havia feito check-in");
      else toast.success("Check-in confirmado!");
      setCode("");
    } catch (e) {
      setError(e.response?.data?.detail || "Erro ao processar");
      toast.error(e.response?.data?.detail || "Código inválido");
    } finally { setLoading(false); }
  };

  const onKey = (e) => { if (e.key === "Enter") process(); };

  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-10" data-testid="checkin-page">
      <div className="text-xs font-mono uppercase tracking-widest text-amber-400 mb-2">Painel do organizador</div>
      <h1 className="text-3xl sm:text-4xl font-extrabold mb-2">Check-in de atletas</h1>
      <p className="text-slate-400 mb-8">Escaneie o QR code do e-mail ou digite o código manualmente.</p>

      <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6 mb-6">
        <Label htmlFor="ci-code" className="mb-2 block">Código de check-in</Label>
        <div className="flex gap-2">
          <div className="relative flex-1">
            <QrCode className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
            <Input id="ci-code" data-testid="checkin-input" value={code} onChange={e=>setCode(e.target.value)}
              onKeyDown={onKey} placeholder="chk_xxxxxxxxxxxxxxxx" autoFocus
              className="pl-9 bg-slate-800 border-slate-700 text-slate-100 font-mono"/>
          </div>
          <Button onClick={()=>process()} disabled={loading} data-testid="checkin-btn"
            className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold">
            {loading ? <Loader2 className="w-4 h-4 animate-spin"/> : <><UserCheck className="w-4 h-4 mr-1"/> Confirmar</>}
          </Button>
        </div>
        <p className="text-xs text-slate-500 mt-2">Dica: use um leitor USB de QR code — ele digita o código e pressiona Enter automaticamente.</p>
      </div>

      {result && (
        <div data-testid="checkin-result" className={`rounded-2xl p-6 border ${
          result.already ? "border-amber-500/40 bg-amber-500/10" : "border-emerald-500/40 bg-emerald-500/10"
        }`}>
          <div className="flex items-start gap-3">
            {result.already ? <UserCheck className="w-8 h-8 text-amber-400 flex-shrink-0"/>
                            : <CheckCircle2 className="w-8 h-8 text-emerald-400 flex-shrink-0"/>}
            <div>
              <div className="text-lg font-bold">
                {result.already ? "Já havia feito check-in" : "Check-in confirmado"}
              </div>
              <div className="text-slate-300 mt-2">
                <div><strong>{result.registration.user_name}</strong></div>
                {result.registration.partner_name && <div>+ {result.registration.partner_name}</div>}
                <div className="text-sm text-slate-400 mt-1">{result.registration.user_email}</div>
                <div className="text-xs text-slate-500 mt-2">
                  Modalidade: {result.registration.mode === "individual" ? "Individual" : "Dupla"} · Status pagamento: {result.registration.payment_status}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {error && !result && (
        <div className="rounded-2xl p-6 border border-red-500/40 bg-red-500/10 flex items-center gap-3">
          <XCircle className="w-6 h-6 text-red-400"/>
          <div>
            <div className="font-bold text-red-300">Não foi possível fazer o check-in</div>
            <div className="text-slate-300 text-sm">{error}</div>
          </div>
        </div>
      )}
    </div>
  );
}
