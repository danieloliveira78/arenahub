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
  const [busy, setBusy] = useState(false);
  const [cycle, setCycle] = useState("yearly"); // "monthly" | "yearly"

  useEffect(() => {
    api.get("/plans").then(({ data }) => setPlans(data)).finally(() => setLoading(false));
  }, []);

  const monthly = plans.find(p => p.lookup_key === "starter_monthly");
  const yearly = plans.find(p => p.lookup_key === "starter_yearly");
  const active = cycle === "yearly" ? yearly : monthly;

  const subscribe = async () => {
    if (!active) return;
    setBusy(true);
    try {
      const { data } = await api.post("/subscriptions/checkout", {
        lookup_key: active.lookup_key,
        origin_url: window.location.origin,
      });
      window.location.href = data.checkout_url;
    } catch (e) {
      toast.error(e.response?.data?.detail || "Erro ao criar checkout");
      setBusy(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-12" data-testid="plans-page">
      <div className="text-center mb-8">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-mono uppercase tracking-widest mb-4">
          <Sparkles className="w-3 h-3" /> 14 dias grátis · sem cartão
        </div>
        <h1 className="text-4xl sm:text-5xl font-extrabold mb-3">Escolha seu plano</h1>
        <p className="text-slate-400">Comece grátis, cancele quando quiser.</p>
      </div>

      {/* Cycle toggle */}
      <div className="flex justify-center mb-8">
        <div role="tablist" aria-label="Ciclo de cobrança"
          className="relative inline-flex rounded-full border border-slate-800 bg-slate-900/70 p-1"
          data-testid="cycle-toggle">
          <ToggleBtn active={cycle === "monthly"} onClick={() => setCycle("monthly")} testid="cycle-monthly">
            Mensal
          </ToggleBtn>
          <ToggleBtn active={cycle === "yearly"} onClick={() => setCycle("yearly")} testid="cycle-yearly">
            Anual
            <span className="ml-2 inline-block bg-amber-500 text-slate-950 text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full">
              2 meses grátis
            </span>
          </ToggleBtn>
        </div>
      </div>

      {loading ? (
        <div className="text-center text-slate-500">Carregando planos...</div>
      ) : !active ? (
        <div className="text-center text-slate-500">Nenhum plano disponível.</div>
      ) : (
        <PlanCard plan={active} onSubscribe={subscribe} busy={busy} />
      )}

      <div className="mt-8 text-center">
        <button onClick={() => nav("/dashboard")} data-testid="skip-plans"
          className="text-sm text-slate-500 hover:text-slate-300">
          Continuar sem plano (acesso limitado)
        </button>
      </div>
    </div>
  );
}

function ToggleBtn({ active, onClick, children, testid }) {
  return (
    <button role="tab" aria-selected={active} onClick={onClick} data-testid={testid}
      className={`relative z-10 px-6 py-2 text-sm font-semibold rounded-full transition-colors ${
        active ? "bg-emerald-500 text-slate-950" : "text-slate-300 hover:text-white"
      }`}>
      {children}
    </button>
  );
}

function PlanCard({ plan, onSubscribe, busy }) {
  const price = plan.amount;
  const isYearly = plan.interval === "year";
  const monthlyEquivalent = isYearly ? price / 12 : price;
  const savings = isYearly ? (49 * 12 - price) : 0;

  return (
    <div data-testid={`plan-card-${plan.lookup_key}`}
      className="relative rounded-2xl p-8 border-2 border-emerald-500 bg-gradient-to-br from-emerald-500/10 via-slate-900 to-slate-900 glow-emerald">
      {isYearly && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-amber-500 text-slate-950 px-3 py-1 rounded-full text-xs font-bold">
          Economize R$ {savings.toFixed(0)} por ano
        </div>
      )}
      <div className="text-xs font-mono uppercase tracking-widest text-emerald-400 mb-1">
        {isYearly ? "Anual" : "Mensal"}
      </div>
      <h2 className="text-2xl font-extrabold mb-4">Starter</h2>
      <div className="mb-1">
        <span className="text-5xl font-extrabold" data-testid="plan-price">
          R$ {monthlyEquivalent.toFixed(0)}
        </span>
        <span className="text-slate-500 ml-2">/mês</span>
      </div>
      {isYearly && (
        <div className="text-xs text-slate-500 mb-4">
          Cobrado anualmente: R$ {price.toFixed(2)}
        </div>
      )}
      <div className="text-xs text-slate-500 mb-6">14 dias grátis · sem cartão</div>
      <ul className="space-y-2 mb-8">
        {FEATURES.map((f, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <Check className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />
            <span className="text-slate-300">{f}</span>
          </li>
        ))}
      </ul>
      <Button onClick={onSubscribe} disabled={busy}
        data-testid={`subscribe-${plan.lookup_key}`}
        className="w-full h-12 font-bold bg-emerald-500 hover:bg-emerald-400 text-slate-950">
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : "Começar agora"}
      </Button>
    </div>
  );
}
