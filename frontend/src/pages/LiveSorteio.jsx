import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Shuffle, X, Loader2, Sparkles } from "lucide-react";

const SHUFFLE_NAMES = ["Sorteando...", "Embaralhando...", "Preparando...", "Definindo..."];

export default function LiveSorteio() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [comp, setComp] = useState(null);
  const [teams, setTeams] = useState([]);
  const [phase, setPhase] = useState("idle"); // idle | shuffling | revealing | done
  const [revealed, setRevealed] = useState(0);
  const [shuffleName, setShuffleName] = useState(SHUFFLE_NAMES[0]);
  const intervalRef = useRef(null);

  useEffect(() => {
    (async () => {
      const [{data:c}, {data:t}] = await Promise.all([
        api.get(`/competitions/${id}`),
        api.get(`/competitions/${id}/teams`),
      ]);
      setComp(c); setTeams(t);
      if (t.length > 0) { setPhase("done"); setRevealed(t.length); }
    })();
  }, [id]);

  const runDraw = async () => {
    setPhase("shuffling"); setRevealed(0); setTeams([]);
    // Cycle placeholder text
    let i = 0;
    intervalRef.current = setInterval(() => {
      i = (i + 1) % SHUFFLE_NAMES.length;
      setShuffleName(SHUFFLE_NAMES[i]);
    }, 200);
    try {
      // Give animation minimum 2s
      const [{data}] = await Promise.all([
        api.post(`/competitions/${id}/draw`),
        new Promise(r => setTimeout(r, 2200)),
      ]);
      clearInterval(intervalRef.current);
      setTeams(data);
      setPhase("revealing");
      // Reveal pairs one by one
      for (let k = 1; k <= data.length; k++) {
        await new Promise(r => setTimeout(r, 900));
        setRevealed(k);
      }
      setPhase("done");
    } catch (e) {
      clearInterval(intervalRef.current);
      setPhase("idle");
      alert(e.response?.data?.detail || "Erro no sorteio");
    }
  };

  return (
    <div className="fixed inset-0 bg-[#0B0F17] z-50 overflow-auto" data-testid="live-sorteio">
      {/* Ambient background */}
      <div className="absolute inset-0 opacity-40 pointer-events-none" style={{
        backgroundImage: "radial-gradient(circle at 20% 20%, rgba(34,197,94,0.2), transparent 40%), radial-gradient(circle at 80% 80%, rgba(6,182,212,0.15), transparent 40%)",
      }} />

      <button onClick={()=>navigate(`/admin/competicoes/${id}`)} data-testid="close-live"
        className="absolute top-6 right-6 w-11 h-11 rounded-full bg-slate-900 border border-slate-800 flex items-center justify-center hover:bg-slate-800 z-10">
        <X className="w-5 h-5 text-slate-300"/>
      </button>

      <div className="relative max-w-6xl mx-auto px-6 py-12 min-h-screen flex flex-col">
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-mono uppercase tracking-widest mb-4">
            <Sparkles className="w-3 h-3"/> Sorteio ao vivo
          </div>
          <h1 className="text-4xl sm:text-6xl lg:text-7xl font-extrabold tracking-tight mb-3">{comp?.title || "..."}</h1>
          <p className="text-slate-400 text-lg">{comp?.type_name}</p>
        </div>

        {phase === "idle" && (
          <div className="flex-1 flex flex-col items-center justify-center gap-8 animate-fade-up">
            <div className="text-center">
              <div className="text-8xl mb-6">🎲</div>
              <p className="text-slate-400 text-xl mb-8">Pronto para sortear as duplas?</p>
            </div>
            <Button onClick={runDraw} data-testid="start-live-draw"
              className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-extrabold text-xl px-12 py-8 rounded-full glow-emerald">
              <Shuffle className="w-6 h-6 mr-2"/> INICIAR SORTEIO
            </Button>
          </div>
        )}

        {phase === "shuffling" && (
          <div className="flex-1 flex flex-col items-center justify-center gap-6">
            <Loader2 className="w-24 h-24 text-emerald-400 animate-spin"/>
            <div className="text-4xl sm:text-6xl font-extrabold text-emerald-400 glow-text-emerald tracking-tight">
              {shuffleName}
            </div>
          </div>
        )}

        {(phase === "revealing" || phase === "done") && teams.length > 0 && (
          <div className="flex-1 flex flex-col items-center py-8">
            <div className="w-full grid grid-cols-1 md:grid-cols-2 gap-5 max-w-4xl">
              {teams.map((t, i) => (
                <div key={t.team_id} data-testid={`live-team-${i}`}
                  style={{ opacity: i < revealed ? 1 : 0.05, transitionDelay: `${i * 20}ms` }}
                  className={`p-6 rounded-2xl border transition-all duration-700 transform ${
                    i < revealed
                      ? "bg-gradient-to-br from-emerald-500/20 via-slate-900 to-cyan-500/10 border-emerald-500/50 scale-100 glow-emerald"
                      : "bg-slate-900/40 border-slate-800 scale-95"
                  }`}>
                  <div className="text-xs font-mono uppercase tracking-widest text-emerald-400 mb-2">Dupla {i+1}</div>
                  <div className="text-2xl sm:text-3xl font-extrabold">{i < revealed ? t.name : "???"}</div>
                </div>
              ))}
            </div>
            {phase === "done" && (
              <div className="mt-10 flex gap-3">
                <Button onClick={runDraw} data-testid="redo-draw"
                  className="bg-slate-800 hover:bg-slate-700 text-slate-100 font-semibold">
                  <Shuffle className="w-4 h-4 mr-1"/> Sortear de novo
                </Button>
                <Button onClick={()=>navigate(`/admin/competicoes/${id}`)}
                  className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold">
                  Voltar ao painel
                </Button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
