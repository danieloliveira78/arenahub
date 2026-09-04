import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Trophy, Medal, Award } from "lucide-react";

export default function Ranking() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/rankings").then(({data}) => setRows(data)).finally(()=>setLoading(false));
  }, []);

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10" data-testid="ranking-page">
      <div className="text-xs font-mono uppercase tracking-widest text-amber-400 mb-2">Hall of Fame</div>
      <h1 className="text-3xl sm:text-4xl font-extrabold mb-2">Ranking de atletas</h1>
      <p className="text-slate-400 mb-8">Vitórias e campeonatos conquistados na plataforma.</p>

      {loading ? (
        <div className="text-slate-500">Carregando ranking...</div>
      ) : rows.length === 0 ? (
        <div className="text-center py-16 border border-dashed border-slate-800 rounded-2xl">
          <Trophy className="w-10 h-10 mx-auto text-slate-600 mb-3" />
          <p className="text-slate-400">Ainda sem partidas encerradas.</p>
          <p className="text-slate-500 text-sm mt-1">Assim que o primeiro torneio terminar, os campeões aparecem aqui.</p>
        </div>
      ) : (
        <div className="bg-slate-900/70 border border-slate-800 rounded-2xl overflow-hidden">
          <div className="grid grid-cols-12 px-6 py-3 border-b border-slate-800 bg-slate-900 text-xs uppercase tracking-widest text-slate-500 font-mono">
            <div className="col-span-1">#</div>
            <div className="col-span-7">Atleta</div>
            <div className="col-span-2 text-right">Campeonatos</div>
            <div className="col-span-2 text-right">Vitórias</div>
          </div>
          {rows.map((r, i) => (
            <div key={r.player} data-testid={`rank-row-${i}`}
              className={`grid grid-cols-12 px-6 py-4 items-center border-b border-slate-800/60 last:border-0 ${i < 3 ? "bg-gradient-to-r from-amber-500/5 to-transparent" : ""}`}>
              <div className="col-span-1">
                {i === 0 ? <Trophy className="w-5 h-5 text-amber-400"/> :
                 i === 1 ? <Medal className="w-5 h-5 text-slate-300"/> :
                 i === 2 ? <Award className="w-5 h-5 text-amber-700"/> :
                 <span className="text-slate-500 font-mono">{i+1}</span>}
              </div>
              <div className="col-span-7">
                <div className="font-semibold text-slate-100">{r.player}</div>
              </div>
              <div className="col-span-2 text-right">
                <span className={`inline-flex items-center gap-1 font-bold ${r.championships > 0 ? "text-amber-400" : "text-slate-500"}`}>
                  {r.championships > 0 && <Trophy className="w-3.5 h-3.5"/>}
                  {r.championships}
                </span>
              </div>
              <div className="col-span-2 text-right text-emerald-400 font-mono font-bold">{r.wins}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
