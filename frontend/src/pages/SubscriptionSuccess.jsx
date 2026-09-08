import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { CheckCircle2, Loader2 } from "lucide-react";
import { api } from "@/lib/api";

export default function SubscriptionSuccess() {
  const [params] = useSearchParams();
  const sessionId = params.get("session_id");
  const [status, setStatus] = useState("polling");

  useEffect(() => {
    let attempts = 0;
    const poll = async () => {
      attempts++;
      try {
        const { data } = await api.get("/me/tenant");
        const s = data.effective_status;
        if (s === "active" || s === "trialing") { setStatus("done"); return; }
        if (attempts >= 15) { setStatus("pending"); return; }
        setTimeout(poll, 2000);
      } catch {
        if (attempts >= 5) setStatus("done");
        else setTimeout(poll, 2000);
      }
    };
    poll();
  }, [sessionId]);

  return (
    <div className="min-h-[70vh] flex items-center justify-center px-4">
      <div className="max-w-md w-full bg-slate-900/80 border border-slate-800 rounded-2xl p-8 text-center" data-testid="sub-success">
        {status === "polling" ? (
          <>
            <Loader2 className="w-12 h-12 mx-auto text-emerald-400 animate-spin mb-4"/>
            <h1 className="text-2xl font-bold mb-2">Ativando sua assinatura...</h1>
            <p className="text-slate-400 text-sm">Aguarde alguns segundos.</p>
          </>
        ) : (
          <>
            <CheckCircle2 className="w-14 h-14 mx-auto text-emerald-400 mb-4"/>
            <h1 className="text-2xl font-bold mb-2">Assinatura ativa!</h1>
            <p className="text-slate-400 mb-6">Sua plataforma está pronta. Vamos criar seu primeiro torneio?</p>
            <Link to="/admin"><Button data-testid="go-admin-btn" className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold">
              Ir ao painel
            </Button></Link>
          </>
        )}
      </div>
    </div>
  );
}
