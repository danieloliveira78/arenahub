import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { CreditCard, Calendar, XCircle, Building, Loader2, ExternalLink } from "lucide-react";

const brl = (v) => `R$ ${Number(v || 0).toFixed(2).replace(".", ",")}`;

const STATUS = {
  trialing: { label: "Em teste grátis", cls: "bg-cyan-500/20 text-cyan-300 border-cyan-500/40" },
  active: { label: "Ativa", cls: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" },
  past_due: { label: "Pagamento pendente", cls: "bg-amber-500/20 text-amber-300 border-amber-500/40" },
  grace_period: { label: "Período de graça", cls: "bg-amber-500/20 text-amber-300 border-amber-500/40" },
  canceled: { label: "Cancelada", cls: "bg-red-500/20 text-red-300 border-red-500/40" },
  inactive: { label: "Inativa", cls: "bg-slate-500/20 text-slate-300 border-slate-500/40" },
};

export default function MinhaAssinatura() {
  const [info, setInfo] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const { data } = await api.get("/me/tenant");
    setInfo(data);
  };
  useEffect(() => { load(); }, []);

  const openPortal = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/subscriptions/portal");
      window.location.href = data.portal_url;
    } catch (e) {
      toast.error(e.response?.data?.detail || "Erro ao abrir portal");
    } finally { setBusy(false); }
  };

  const cancel = async () => {
    if (!confirm("Cancelar assinatura no fim do período atual?")) return;
    try {
      await api.post("/subscriptions/cancel");
      toast.success("Cancelamento agendado para o fim do período.");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Erro"); }
  };

  if (!info) return <div className="p-10 text-slate-400">Carregando...</div>;
  const t = info.tenant || {};
  const st = STATUS[info.effective_status] || STATUS.inactive;

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-10" data-testid="minha-assinatura">
      <div className="text-xs font-mono uppercase tracking-widest text-emerald-400 mb-2">Faturamento</div>
      <h1 className="text-3xl sm:text-4xl font-extrabold mb-6">Minha assinatura</h1>

      <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6 mb-6">
        <div className="flex items-start justify-between flex-wrap gap-3 mb-6">
          <div>
            <div className="flex items-center gap-2 text-slate-400 mb-1"><Building className="w-4 h-4"/> Organização</div>
            <div className="text-xl font-bold">{t.name}</div>
            <div className="text-xs text-slate-500 mt-1">Slug: <code className="text-emerald-400">{t.slug}</code></div>
          </div>
          <Badge className={`border ${st.cls} text-sm`}>{st.label}</Badge>
        </div>

        <div className="grid sm:grid-cols-2 gap-4">
          <Row icon={CreditCard} label="Plano atual" value={t.plan_lookup_key === "starter_yearly" ? "Anual (R$ 490/ano)" : (t.plan_lookup_key === "starter_monthly" ? "Mensal (R$ 49/mês)" : "Starter (trial)")}/>
          <Row icon={Calendar} label="Próxima renovação" value={t.current_period_end ? new Date(t.current_period_end).toLocaleDateString("pt-BR") : "—"}/>
        </div>

        {info.effective_status === "grace_period" && (
          <div className="mt-4 p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-sm">
            ⚠ Pagamento em atraso. Você está no período de graça de 7 dias — regularize para não perder o acesso.
          </div>
        )}
        {info.effective_status === "inactive" && (
          <div className="mt-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-sm">
            ✕ Assinatura inativa. Os dados estão preservados, mas a edição está bloqueada até nova assinatura.
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-3">
        {t.stripe_customer_id ? (
          <Button onClick={openPortal} disabled={busy} data-testid="portal-btn"
            className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold">
            {busy ? <Loader2 className="w-4 h-4 animate-spin"/> : <><ExternalLink className="w-4 h-4 mr-1"/> Portal do cliente (Stripe)</>}
          </Button>
        ) : (
          <Link to="/planos"><Button data-testid="choose-plan-btn" className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold">
            Escolher plano
          </Button></Link>
        )}
        {t.stripe_subscription_id && !t.cancel_at_period_end && info.effective_status !== "canceled" && (
          <Button onClick={cancel} data-testid="cancel-sub-btn" variant="outline" className="border-red-800/40 text-red-300 hover:bg-red-950/30">
            <XCircle className="w-4 h-4 mr-1"/> Cancelar assinatura
          </Button>
        )}
      </div>
    </div>
  );
}

const Row = ({ icon: Icon, label, value }) => (
  <div>
    <div className="flex items-center gap-2 text-xs uppercase tracking-widest text-slate-500 font-mono mb-1">
      <Icon className="w-3.5 h-3.5"/> {label}
    </div>
    <div className="font-semibold">{value}</div>
  </div>
);
