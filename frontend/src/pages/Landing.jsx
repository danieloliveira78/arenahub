import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Trophy, Users, Zap, ArrowRight, Shuffle, Calendar, DollarSign } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

export default function Landing() {
  const { user, login } = useAuth();

  return (
    <div className="relative overflow-hidden">
      {/* HERO */}
      <section className="relative">
        <div className="absolute inset-0 opacity-30" style={{
          backgroundImage: "radial-gradient(ellipse at top left, rgba(34,197,94,0.15), transparent 50%), radial-gradient(ellipse at bottom right, rgba(6,182,212,0.1), transparent 50%)",
        }} />
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 lg:py-28 relative">
          <div className="grid lg:grid-cols-12 gap-10 items-center">
            <div className="lg:col-span-7 animate-fade-up">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-semibold mb-6">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                PLATAFORMA DE TORNEIOS BRASILEIRA
              </div>
              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight leading-[1.05] mb-6" data-testid="hero-title">
                Transforme seus torneios em<br />
                <span className="text-emerald-400 glow-text-emerald">grandes espetáculos.</span>
              </h1>
              <p className="text-lg text-slate-400 max-w-xl mb-8">
                Cadastre competições, receba inscrições com PIX ou cartão, sorteie duplas e monte chaveamentos automáticos. Tudo em um só lugar.
              </p>
              <div className="flex flex-wrap gap-3">
                <Link to="/competicoes">
                  <Button data-testid="hero-cta-explore" size="lg" className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold rounded-full px-7">
                    Explorar Torneios <ArrowRight className="ml-2 w-4 h-4" />
                  </Button>
                </Link>
                {!user && (
                  <Button data-testid="hero-cta-login" onClick={login} size="lg" variant="outline"
                    className="border-white/20 hover:bg-white/5 rounded-full px-7 text-slate-100">
                    Criar Conta Grátis
                  </Button>
                )}
              </div>
              <div className="mt-10 flex flex-wrap gap-6 text-sm text-slate-400">
                <div className="flex items-center gap-2"><Trophy className="w-4 h-4 text-amber-400"/> Chaveamento automático</div>
                <div className="flex items-center gap-2"><Shuffle className="w-4 h-4 text-emerald-400"/> Sorteio de duplas</div>
                <div className="flex items-center gap-2"><DollarSign className="w-4 h-4 text-cyan-400"/> Pagamento seguro</div>
              </div>
            </div>

            <div className="lg:col-span-5 relative animate-fade-up" style={{animationDelay:"120ms"}}>
              <div className="relative rounded-3xl overflow-hidden border border-white/10 shadow-2xl glow-emerald">
                <img src="https://images.unsplash.com/photo-1521138054413-5a47d349b7af?crop=entropy&cs=srgb&fm=jpg&q=85"
                     className="w-full h-full object-cover aspect-[4/5]" alt="Torneio" />
                <div className="absolute inset-0 bg-gradient-to-t from-[#0B0F17] via-transparent to-transparent" />
                <div className="absolute bottom-6 left-6 right-6">
                  <div className="bg-slate-900/90 backdrop-blur-xl border border-white/10 rounded-2xl p-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-emerald-500/20 flex items-center justify-center">
                        <Trophy className="w-5 h-5 text-emerald-400" />
                      </div>
                      <div>
                        <div className="text-xs text-slate-400 font-mono uppercase tracking-widest">Torneio ao vivo</div>
                        <div className="text-white font-semibold">Copa Futevôlei de Verão</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Bento */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="grid md:grid-cols-3 gap-5">
          {[
            {icon: Calendar, title:"Inscrições online", desc:"Datas de abertura, fechamento e vagas controladas automaticamente.", color:"emerald"},
            {icon: Shuffle, title:"Sorteio de duplas", desc:"Inscrições individuais viram duplas por sorteio aleatório justo.", color:"cyan"},
            {icon: Trophy, title:"Chaveamento até a final", desc:"Fases automáticas com controle de placares e vencedores.", color:"amber"},
          ].map((f, i) => (
            <div key={i} data-testid={`feature-card-${i}`}
              className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6 hover:border-emerald-500/40 hover:bg-slate-900 transition-all">
              <div className={`w-11 h-11 rounded-xl flex items-center justify-center mb-4 bg-${f.color}-500/10 border border-${f.color}-500/30`}>
                <f.icon className={`w-5 h-5 text-${f.color}-400`} />
              </div>
              <h3 className="text-lg font-semibold mb-2">{f.title}</h3>
              <p className="text-slate-400 text-sm">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
