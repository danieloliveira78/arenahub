import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Trophy, Users, Zap, ArrowRight, Shuffle, Calendar, DollarSign, Check, Sparkles } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const FAQ = [
  { q: "Preciso de cartão pra começar?", a: "Não. 14 dias grátis, sem cartão. Depois você escolhe entre mensal e anual." },
  { q: "Posso cancelar quando quiser?", a: "Sim. Cancele no fim do período com um clique — sem multa." },
  { q: "Como funciona o pagamento das inscrições dos atletas?", a: "Você recebe direto na sua conta Stripe via PIX ou cartão. A gente só cobra a assinatura da plataforma." },
  { q: "O que acontece se eu não pagar?", a: "Você tem 7 dias de graça. Depois disso, a edição fica bloqueada, mas seus dados ficam preservados até você regularizar." },
  { q: "Meus dados ficam isolados dos outros clientes?", a: "Sim. Cada organização tem seu próprio ambiente. Nenhum outro admin acessa seus torneios." },
];

export default function Landing() {
  const { user } = useAuth();
  const [plans, setPlans] = useState([]);
  useEffect(() => { api.get("/plans").then(({data}) => setPlans(data)).catch(()=>{}); }, []);

  const monthly = plans.find(p => p.lookup_key === "starter_monthly");

  return (
    <div className="relative overflow-hidden">
      <section className="relative">
        <div className="absolute inset-0 opacity-30" style={{
          backgroundImage: "radial-gradient(ellipse at top left, rgba(34,197,94,0.15), transparent 50%), radial-gradient(ellipse at bottom right, rgba(6,182,212,0.1), transparent 50%)",
        }}/>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 lg:py-24 relative">
          <div className="grid lg:grid-cols-12 gap-10 items-center">
            <div className="lg:col-span-7 animate-fade-up">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-semibold mb-6">
                <Sparkles className="w-3 h-3"/> SAAS DE GESTÃO DE TORNEIOS · BR
              </div>
              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight leading-[1.05] mb-6" data-testid="hero-title">
                Torneios profissionais<br/>
                <span className="text-emerald-400 glow-text-emerald">sem planilha, sem estresse.</span>
              </h1>
              <p className="text-lg text-slate-400 max-w-xl mb-8">
                Cada organização com seu próprio ambiente. Inscrições online, sorteio de duplas, chaveamento e cobrança em um só lugar.
              </p>
              <div className="flex flex-wrap gap-3">
                <Link to={user ? "/dashboard" : "/cadastro"}>
                  <Button data-testid="hero-cta-start" size="lg" className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold rounded-full px-7">
                    Começar agora — 14 dias grátis <ArrowRight className="ml-2 w-4 h-4"/>
                  </Button>
                </Link>
                <Link to="/planos">
                  <Button data-testid="hero-cta-plans" size="lg" variant="outline" className="border-white/20 hover:bg-white/5 rounded-full px-7 text-slate-100">
                    Ver planos
                  </Button>
                </Link>
              </div>
              <div className="mt-8 text-xs text-slate-500 flex flex-wrap gap-4">
                <span>✓ Sem cartão pra começar</span>
                <span>✓ Cancele quando quiser</span>
                <span>✓ Dados isolados por cliente</span>
              </div>
            </div>
            <div className="lg:col-span-5 relative animate-fade-up" style={{animationDelay:"120ms"}}>
              <div className="relative rounded-3xl overflow-hidden border border-white/10 shadow-2xl glow-emerald">
                <img src="https://images.unsplash.com/photo-1521138054413-5a47d349b7af?crop=entropy&cs=srgb&fm=jpg&q=85"
                     className="w-full h-full object-cover aspect-[4/5]" alt="Torneio"/>
                <div className="absolute inset-0 bg-gradient-to-t from-[#0B0F17] via-transparent to-transparent"/>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <h2 className="text-3xl font-extrabold text-center mb-10">Tudo pra rodar sua liga</h2>
        <div className="grid md:grid-cols-3 gap-5">
          {[
            {icon: Calendar, title:"Inscrições online", desc:"Datas de abertura, fechamento, vagas e valores em minutos.", color:"emerald"},
            {icon: Shuffle, title:"Sorteio de duplas", desc:"Individual vira dupla por sorteio aleatório justo.", color:"cyan"},
            {icon: Trophy, title:"Chaveamento automático", desc:"Fases geradas por sorteio, placares editáveis até a final.", color:"amber"},
            {icon: DollarSign, title:"Pagamento seguro", desc:"PIX e cartão via Stripe direto na sua conta.", color:"emerald"},
            {icon: Users, title:"Ranking de atletas", desc:"Perfis públicos com histórico, campeonatos e parcerias.", color:"cyan"},
            {icon: Zap, title:"Ambiente isolado", desc:"Cada organizador tem seu próprio ambiente. Dados 100% separados.", color:"amber"},
          ].map((f, i) => (
            <div key={i} data-testid={`feature-card-${i}`} className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6 hover:border-emerald-500/40 hover:bg-slate-900 transition-all">
              <div className={`w-11 h-11 rounded-xl flex items-center justify-center mb-4 bg-${f.color}-500/10 border border-${f.color}-500/30`}>
                <f.icon className={`w-5 h-5 text-${f.color}-400`}/>
              </div>
              <h3 className="text-lg font-semibold mb-2">{f.title}</h3>
              <p className="text-slate-400 text-sm">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-16" id="planos">
        <h2 className="text-3xl font-extrabold text-center mb-2">Preço simples</h2>
        <p className="text-slate-400 text-center mb-10">Um só plano hoje. Anual dá 2 meses grátis.</p>
        <div className="bg-gradient-to-br from-emerald-500/10 via-slate-900 to-slate-900 border-2 border-emerald-500 rounded-3xl p-10 glow-emerald max-w-lg mx-auto text-center">
          <div className="text-xs font-mono uppercase tracking-widest text-emerald-400 mb-2">Starter</div>
          <div className="text-6xl font-extrabold mb-1">R$ {monthly ? monthly.amount.toFixed(0) : "49"}<span className="text-lg text-slate-500">/mês</span></div>
          <div className="text-sm text-slate-400 mb-6">14 dias grátis · sem cartão</div>
          <ul className="text-left space-y-2 mb-8 max-w-sm mx-auto">
            {["5 torneios ativos","200 atletas por torneio","PIX + cartão","Sorteio + chaveamento automáticos","Check-in por QR","Painel financeiro + CSV"].map((f, i) => (
              <li key={i} className="flex items-center gap-2 text-sm"><Check className="w-4 h-4 text-emerald-400"/> {f}</li>
            ))}
          </ul>
          <Link to={user ? "/planos" : "/cadastro"}>
            <Button size="lg" data-testid="landing-cta" className="w-full bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold h-12">
              Começar teste grátis
            </Button>
          </Link>
        </div>
      </section>

      <section className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <h2 className="text-3xl font-extrabold text-center mb-8">Perguntas frequentes</h2>
        <div className="space-y-3">
          {FAQ.map((f, i) => (
            <details key={i} data-testid={`faq-${i}`} className="bg-slate-900/70 border border-slate-800 rounded-xl p-5 group">
              <summary className="cursor-pointer font-semibold flex justify-between items-center">
                {f.q}
                <span className="text-emerald-400 transition-transform group-open:rotate-45 text-2xl leading-none">+</span>
              </summary>
              <p className="text-slate-400 text-sm mt-3">{f.a}</p>
            </details>
          ))}
        </div>
      </section>
    </div>
  );
}
