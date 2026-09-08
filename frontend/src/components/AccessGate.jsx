import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Lock, Sparkles, ArrowRight } from "lucide-react";
import { useSubscription } from "@/hooks/useSubscription";

/**
 * Wrap admin/edit-only screens. When the tenant subscription is inactive
 * (trial ended without plan, canceled, or past grace period), renders a
 * full-screen block with a single CTA to /planos. Otherwise renders children.
 */
export default function AccessGate({ children }) {
  const { info, loading, isBlocked, status } = useSubscription();

  if (loading) {
    return <div className="min-h-[60vh] flex items-center justify-center text-slate-400" data-testid="access-gate-loading">Carregando...</div>;
  }
  if (!isBlocked) return children;

  const tenant = info?.tenant || {};
  const reason = (() => {
    if (status === "canceled") return "Sua assinatura foi cancelada. Ative um plano para voltar a editar seus torneios.";
    if (status === "inactive" && tenant.trial_end && new Date(tenant.trial_end) < new Date())
      return "Seu período de 14 dias grátis terminou. Ative o plano Starter para continuar gerenciando torneios.";
    return "Sua assinatura está inativa. Reative para continuar editando — seus dados estão preservados.";
  })();

  return (
    <div className="min-h-[70vh] flex items-center justify-center px-4 py-10" data-testid="access-gate-blocked">
      <div className="max-w-lg w-full text-center">
        <div className="mx-auto mb-6 w-16 h-16 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center">
          <Lock className="w-8 h-8 text-amber-400" strokeWidth={2}/>
        </div>
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs font-mono uppercase tracking-widest mb-4">
          <Sparkles className="w-3 h-3"/> Acesso somente-leitura
        </div>
        <h1 className="text-3xl sm:text-4xl font-extrabold mb-3">Ative o Starter para continuar</h1>
        <p className="text-slate-400 mb-2">{reason}</p>
        <p className="text-slate-500 text-sm mb-8">Você continua vendo tudo — apenas as ações de edição estão bloqueadas.</p>
        <Link to="/planos">
          <Button data-testid="access-gate-cta" size="lg"
            className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold rounded-full px-8 h-12">
            Assinar plano Starter <ArrowRight className="ml-2 w-4 h-4"/>
          </Button>
        </Link>
        <div className="mt-6 text-xs text-slate-500">
          R$ 49/mês · cancele quando quiser · <Link to="/minha-assinatura" className="underline hover:text-slate-300">gerenciar assinatura</Link>
        </div>
      </div>
    </div>
  );
}
