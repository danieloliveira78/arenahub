import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";

export default function PaymentSuccess() {
  const [params] = useSearchParams();
  const sessionId = params.get("session_id");
  const [status, setStatus] = useState("polling");
  const [attempts, setAttempts] = useState(0);

  useEffect(() => {
    if (!sessionId) { setStatus("error"); return; }
    let mounted = true;
    let attempt = 0;
    const poll = async () => {
      attempt += 1;
      setAttempts(attempt);
      try {
        const { data } = await api.get(`/payments/status/${sessionId}`);
        if (!mounted) return;
        if (data.payment_status === "paid") { setStatus("paid"); return; }
        if (data.payment_status === "failed" || data.payment_status === "expired") { setStatus("failed"); return; }
        if (attempt >= 10) { setStatus("pending"); return; }
        setTimeout(poll, 2000);
      } catch (e) {
        if (attempt >= 5) setStatus("error");
        else setTimeout(poll, 2000);
      }
    };
    poll();
    return () => { mounted = false; };
  }, [sessionId]);

  return (
    <div className="min-h-[70vh] flex items-center justify-center px-4">
      <div className="max-w-md w-full bg-slate-900/80 border border-slate-800 rounded-2xl p-8 text-center" data-testid="payment-success">
        {status === "polling" && (
          <>
            <Loader2 className="w-12 h-12 mx-auto text-emerald-400 animate-spin mb-4" />
            <h1 className="text-2xl font-bold mb-2">Confirmando pagamento...</h1>
            <p className="text-slate-400 text-sm">Tentativa {attempts}/10</p>
          </>
        )}
        {status === "paid" && (
          <>
            <CheckCircle2 className="w-14 h-14 mx-auto text-emerald-400 mb-4" />
            <h1 className="text-2xl font-bold mb-2">Pagamento confirmado!</h1>
            <p className="text-slate-400 mb-6">Sua inscrição está garantida. Enviamos um e-mail com os detalhes.</p>
            <Link to="/dashboard"><Button data-testid="go-dashboard" className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold">Ir para meu painel</Button></Link>
          </>
        )}
        {(status === "failed" || status === "error") && (
          <>
            <XCircle className="w-14 h-14 mx-auto text-red-400 mb-4" />
            <h1 className="text-2xl font-bold mb-2">Ocorreu um problema</h1>
            <p className="text-slate-400 mb-6">Não foi possível confirmar o pagamento. Tente novamente.</p>
            <Link to="/competicoes"><Button className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold">Voltar aos torneios</Button></Link>
          </>
        )}
        {status === "pending" && (
          <>
            <Loader2 className="w-12 h-12 mx-auto text-amber-400 mb-4" />
            <h1 className="text-2xl font-bold mb-2">Aguardando confirmação</h1>
            <p className="text-slate-400 mb-6">O pagamento ainda está sendo processado. Você receberá um e-mail assim que for confirmado.</p>
            <Link to="/dashboard"><Button className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold">Ver minhas inscrições</Button></Link>
          </>
        )}
      </div>
    </div>
  );
}
