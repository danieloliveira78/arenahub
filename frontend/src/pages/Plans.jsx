import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Check, Sparkles, Loader2 } from "lucide-react";
import { toast } from "sonner";

const FEATURES = [
  "Torneios ilimitados no plano anual (5 no mensal)",
  "Até 200 atletas por torneio",
  "Sorteio automático de duplas",
  "Chaveamento com propagação automática",
  "Pagamentos via PIX/cartão (Stripe)",
  "Check-in por QR Code + câmera",
  "E-mails automáticos (inscrição, sorteio)",
  "Painel financeiro com CSV",
  "Perfis de atletas + rankings",
  "Story card do campeão",
];

export default function Plans() {
  const nav = useNavigate();
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);

  useEffect(() => {
    api.get("/plans").then(({data}) => setPlans(data)).finally(()=>setLoading(false));
  }, []);

  const subscribe = async (lookup_key) => {
    setBusy(lookup_key);
    try {
      const { data } = await api.post("/subscriptions/checkout", { lookup_key, origin_url: window.location.origin });
      window.location.href = data.checkout_url;
    } catch (e) {
      toast.error(e.response?.data?.detail || "Erro ao criar checkout");
      setBusy(null);
    }
  };

  const monthly = plans.find(p => p.lookup_key === "starter_monthly");
  const yearly = plans.find(p => p.lookup_key === "starter_yearly");

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-12" data-testid="plans-page">
      <div className="text-center mb-12">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-mono uppercase tracking-widest mb-4">
          <Sparkles className="w-3 h-3"/> 14 dias grátis · sem cartão
        </div>
        <h1 className="text-4xl sm:text-5xl font-extrabold mb-3">Escolha seu plano</h1>
        <p className="text-slate-400">Comece grátis, cancele quando quiser.</p>
      </div>

      {loading ? <div className="text-center text-slate-500">Carregando planos...</div> : (
      <div className="grid md:grid-cols-2 gap-6 max-w-3xl mx-auto">
        <PlanCard plan={monthly} label="Mensal" subscribe={subscribe} busy={busy}/>
        <PlanCard plan={yearly} label="Anual" highlight badge="2 meses grátis" subscribe={subscribe} busy={busy}/>
      </div>
      )}

      <div className="mt-8 text-center">
        <button onClick={()=>nav("/dashboard")} data-testid="skip-plans" className="text-sm text-slate-500 hover:text-slate-300">
          Continuar sem plano (acesso limitado)
        </button>
      </div>
    </div>
  );
}

function PlanCard({ plan, label, highlight, badge, subscribe, busy }) {
  if (!plan) return null;
  const price = plan.amount;
  const monthlyEquivalent = plan.interval === "year" ? price / 12 : price;
  return (
    <div data-testid={`plan-card-${plan.lookup_key}`}
      className={`relative rounded-2xl p-8 border-2 ${
        highlight ? "border-emerald-500 bg-gradient-to-br from-emerald-500/10 via-slate-900 to-slate-900 glow-emerald"
                  : "border-slate-800 bg-slate-900/70"
      }`}>
      {badge && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-amber-500 text-slate-950 px-3 py-1 rounded-full text-xs font-bold">
          {badge}
        </div>
      )}
      <div className="text-xs font-mono uppercase tracking-widest text-emerald-400 mb-1">{label}</div>
      <h2 className="text-2xl font-extrabold mb-4">Starter</h2>
      <div className="mb-1">
        <span className="text-5xl font-extrabold">R$ {monthlyEquivalent.toFixed(0)}</span>
        <span className="text-slate-500 ml-2">/mês</span>
      </div>
      {plan.interval === "year" && (
        <div className="text-xs text-slate-500 mb-4">Cobrado anualmente: R$ {price.toFixed(2)}</div>
      )}
      <div className="text-xs text-slate-500 mb-6">14 dias grátis</div>
      <ul className="space-y-2 mb-8">
        {FEATURES.map((f, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <Check className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5"/>
            <span className="text-slate-300">{f}</span>
          </li>
        ))}
      </ul>
      <Button onClick={()=>subscribe(plan.lookup_key)} disabled={busy === plan.lookup_key}
        data-testid={`subscribe-${plan.lookup_key}`}
        className={`w-full h-12 font-bold ${highlight ? "bg-emerald-500 hover:bg-emerald-400 text-slate-950" : "bg-slate-800 hover:bg-slate-700 text-white"}`}>
        {busy === plan.lookup_key ? <Loader2 className="w-4 h-4 animate-spin"/> : "Começar agora"}
      </Button>
    </div>
  );
}
