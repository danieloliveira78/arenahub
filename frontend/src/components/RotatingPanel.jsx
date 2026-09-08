import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Shuffle, Trophy, Loader2, Users, Save, Crown, Medal } from "lucide-react";
import { toast } from "sonner";

/**
 * Rotating Doubles (Rei da Praia) admin panel.
 * Groups of 4 players, 3 group rounds (all pair combinations), individual scoring.
 * Top-2 per group advance to knockout with fresh pair draw each round.
 */
export default function RotatingPanel({ competitionId, regs, reloadCompetition }) {
  const [groups, setGroups] = useState([]);
  const [matches, setMatches] = useState([]);
  const [board, setBoard] = useState([]);
  const [busy, setBusy] = useState(null);

  const load = async () => {
    const [{ data: g }, { data: m }, { data: lb }] = await Promise.all([
      api.get(`/competitions/${competitionId}/rotating/groups`),
      api.get(`/competitions/${competitionId}/matches`),
      api.get(`/competitions/${competitionId}/rotating/leaderboard`),
    ]);
    setGroups(g); setMatches(m); setBoard(lb);
  };

  useEffect(() => { load(); }, [competitionId]);

  const drawGroups = async () => {
    if (groups.length > 0 && !confirm("Isso vai apagar grupos, times e partidas atuais. Continuar?")) return;
    setBusy("draw-groups");
    try {
      await api.post(`/competitions/${competitionId}/rotating/draw-groups`);
      toast.success("Grupos sorteados!");
      await load();
    } catch (e) { toast.error(e.response?.data?.detail || "Erro no sorteio"); }
    finally { setBusy(null); }
  };

  const nextKnockoutRound = async () => {
    setBusy("next-ko");
    try {
      const { data } = await api.post(`/competitions/${competitionId}/rotating/next-knockout-round`);
      if (data.finished) toast.success("Torneio encerrado!");
      else toast.success(`Rodada ${data.round} da eliminatória sorteada`);
      await load();
    } catch (e) { toast.error(e.response?.data?.detail || "Erro"); }
    finally { setBusy(null); }
  };

  const saveScore = async (m, score_a, score_b) => {
    try {
      await api.put(`/matches/${m.match_id}`, { score_a: Number(score_a), score_b: Number(score_b) });
      toast.success("Placar salvo");
      await load();
    } catch (e) { toast.error("Erro ao salvar"); }
  };

  const groupMatches = matches.filter(m => m.phase === "group");
  const koMatches = matches.filter(m => m.phase === "knockout");
  const koByRound = koMatches.reduce((acc, m) => { (acc[m.round] = acc[m.round] || []).push(m); return acc; }, {});
  const koRounds = Object.keys(koByRound).map(Number).sort((a, b) => a - b);

  const groupPhaseComplete = groupMatches.length > 0 && groupMatches.every(m => m.winner);
  const currentKoRound = koRounds.length ? koRounds[koRounds.length - 1] : 0;
  const currentKoComplete = currentKoRound && koByRound[currentKoRound].every(m => m.winner);
  const canDrawNextKo = groupPhaseComplete && (currentKoRound === 0 || currentKoComplete);

  return (
    <div className="space-y-10" data-testid="rotating-panel">
      {/* Controls */}
      <div className="flex flex-wrap gap-3">
        <Button onClick={drawGroups} disabled={busy === "draw-groups" || regs.length < 4}
          data-testid="rotating-draw-groups"
          className="bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold">
          {busy === "draw-groups" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Shuffle className="w-4 h-4 mr-1" />}
          Sortear grupos & rodadas
        </Button>
        {groups.length > 0 && (
          <Button onClick={nextKnockoutRound} disabled={busy === "next-ko" || !canDrawNextKo}
            data-testid="rotating-next-ko"
            className="bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold disabled:opacity-40">
            {busy === "next-ko" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trophy className="w-4 h-4 mr-1" />}
            {currentKoRound === 0 ? "Iniciar eliminatória" : `Sortear rodada ${currentKoRound + 1}`}
          </Button>
        )}
        <div className="text-xs text-slate-500 self-center">
          {regs.length} inscritos · precisa múltiplos de 4 (mín. 4)
        </div>
      </div>

      {/* Groups */}
      {groups.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-4">
            <Users className="w-5 h-5 text-emerald-400" />
            <h2 className="text-xl font-bold">Grupos ({groups.length})</h2>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
            {groups.map(g => (
              <div key={g.group_id} data-testid={`group-${g.group_id}`}
                className="bg-slate-900/70 border border-slate-800 rounded-xl p-4">
                <div className="text-xs text-emerald-400 font-mono uppercase mb-3">{g.name}</div>
                <ol className="space-y-1">
                  {(g.player_names || []).map((n, i) => (
                    <li key={i} className="text-sm text-slate-200">
                      <span className="text-slate-500 font-mono text-xs mr-2">{i + 1}.</span>{n}
                    </li>
                  ))}
                </ol>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Group matches */}
      {groupMatches.length > 0 && (
        <section>
          <h2 className="text-xl font-bold mb-4">Fase de grupos · Rodadas</h2>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {groups.map(g => {
              const gm = groupMatches.filter(m => m.group_id === g.group_id).sort((a, b) => a.round - b.round);
              return (
                <div key={g.group_id} className="bg-slate-950/60 border border-slate-800 rounded-2xl p-4">
                  <div className="text-xs font-mono uppercase text-emerald-400 mb-3">{g.name}</div>
                  <div className="space-y-3">
                    {gm.map(m => (
                      <MatchRow key={m.match_id} m={m} onSave={saveScore} label={`R${m.round}`} />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Knockout matches */}
      {koRounds.length > 0 && (
        <section>
          <h2 className="text-xl font-bold mb-4">Eliminatória</h2>
          <div className="flex gap-6 overflow-x-auto pb-4">
            {koRounds.map(r => (
              <div key={r} className="flex-shrink-0 w-72 space-y-3">
                <div className="text-xs uppercase tracking-widest text-slate-500 font-mono font-bold">
                  {r === koRounds[koRounds.length - 1] && !koByRound[r].some(m => !m.winner) && koByRound[r].length === 1
                    ? "Final" : `Rodada ${r}`}
                </div>
                {koByRound[r].map(m => <MatchRow key={m.match_id} m={m} onSave={saveScore} />)}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Individual Leaderboard */}
      {board.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-4">
            <Crown className="w-5 h-5 text-amber-400" />
            <h2 className="text-xl font-bold">Ranking individual</h2>
          </div>
          <div className="bg-slate-900/70 border border-slate-800 rounded-2xl overflow-hidden" data-testid="rotating-leaderboard">
            <table className="w-full text-sm">
              <thead className="bg-slate-900 text-xs uppercase tracking-widest text-slate-500 font-mono">
                <tr>
                  <th className="text-left px-4 py-3 w-12">#</th>
                  <th className="text-left px-4 py-3">Jogador</th>
                  <th className="text-right px-4 py-3">Pontos</th>
                  <th className="text-right px-4 py-3">Vitórias</th>
                  <th className="text-right px-4 py-3">Partidas</th>
                </tr>
              </thead>
              <tbody>
                {board.map((p, i) => (
                  <tr key={p.registration_id} className="border-t border-slate-800/60"
                    data-testid={`lb-row-${p.registration_id}`}>
                    <td className="px-4 py-3 font-mono">
                      {i === 0 ? <Crown className="w-4 h-4 text-amber-400" />
                        : i < 3 ? <Medal className="w-4 h-4 text-slate-400" />
                          : i + 1}
                    </td>
                    <td className="px-4 py-3 font-semibold">{p.name}</td>
                    <td className="px-4 py-3 text-right font-mono text-emerald-300">{p.points}</td>
                    <td className="px-4 py-3 text-right font-mono">{p.wins}</td>
                    <td className="px-4 py-3 text-right font-mono text-slate-400">{p.matches}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

function MatchRow({ m, onSave, label }) {
  const [a, setA] = useState(m.score_a);
  const [b, setB] = useState(m.score_b);
  useEffect(() => { setA(m.score_a); setB(m.score_b); }, [m.score_a, m.score_b]);

  return (
    <div data-testid={`rot-match-${m.match_id}`} className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden">
      {label && <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 px-3 pt-2">{label}</div>}
      <SideRow name={m.team_a_name} score={a} setScore={setA} winner={m.winner === "A"} />
      <div className="h-px bg-slate-800" />
      <SideRow name={m.team_b_name} score={b} setScore={setB} winner={m.winner === "B"} />
      <div className="p-2 border-t border-slate-800 bg-slate-900">
        <Button size="sm" onClick={() => onSave(m, a, b)} data-testid={`rot-save-${m.match_id}`}
          className="w-full h-8 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold">
          <Save className="w-3 h-3 mr-1" /> Salvar placar
        </Button>
      </div>
    </div>
  );
}

const SideRow = ({ name, score, setScore, winner }) => (
  <div className={`flex justify-between items-center px-3 py-2 ${winner ? "bg-emerald-500/10" : ""}`}>
    <span className={`text-sm truncate flex-1 ${winner ? "text-emerald-300 font-semibold" : "text-slate-300"}`}>{name}</span>
    <Input type="number" value={score} onChange={e => setScore(e.target.value)}
      className="w-14 h-8 bg-slate-800 border-slate-700 text-slate-100 text-center font-mono" />
  </div>
);
