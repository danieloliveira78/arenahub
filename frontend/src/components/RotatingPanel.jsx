import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Shuffle, Trophy, Loader2, Users, Save, Crown, Medal, HeartCrack, Sparkles, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export default function RotatingPanel({ competitionId, regs, reloadCompetition }) {
  const [groups, setGroups] = useState([]);
  const [matches, setMatches] = useState([]);
  const [teams, setTeams] = useState([]);
  const [board, setBoard] = useState([]);
  const [busy, setBusy] = useState(null);
  const [retireOpen, setRetireOpen] = useState(false);
  const [retireCtx, setRetireCtx] = useState(null); // {match, players}

  const load = async () => {
    const [{ data: g }, { data: m }, { data: t }, { data: lb }] = await Promise.all([
      api.get(`/competitions/${competitionId}/rotating/groups`),
      api.get(`/competitions/${competitionId}/matches`),
      api.get(`/competitions/${competitionId}/teams`),
      api.get(`/competitions/${competitionId}/rotating/leaderboard`),
    ]);
    setGroups(g); setMatches(m); setTeams(t); setBoard(lb);
  };
  useEffect(() => { load(); }, [competitionId]);

  const teamById = Object.fromEntries(teams.map(t => [t.team_id, t]));
  const boardByReg = Object.fromEntries(board.map(p => [p.registration_id, p]));

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

  const saveScore = async (m, score_a, score_b, winner) => {
    if (Number(score_a) === Number(score_b) && !winner) {
      toast.error("Placar empatado — defina o vencedor pela melhor campanha");
      return;
    }
    try {
      await api.put(`/matches/${m.match_id}`, {
        score_a: Number(score_a), score_b: Number(score_b),
        ...(winner ? { winner } : {}),
      });
      toast.success("Placar salvo");
      await load();
    } catch (e) { toast.error(e.response?.data?.detail || "Erro ao salvar"); }
  };

  const openRetire = (m) => {
    const ta = teamById[m.team_a_id]; const tb = teamById[m.team_b_id];
    const players = [
      ...((ta?.source_registration_ids || []).map((rid, i) => ({ reg_id: rid, name: ta.players?.[i] }))),
      ...((tb?.source_registration_ids || []).map((rid, i) => ({ reg_id: rid, name: tb.players?.[i] }))),
    ];
    setRetireCtx({ match: m, players });
    setRetireOpen(true);
  };

  const doRetire = async (registration_id, reason, notes) => {
    if (!retireCtx) return;
    try {
      const { data } = await api.post(
        `/competitions/${competitionId}/matches/${retireCtx.match.match_id}/retire-player`,
        { registration_id, reason, notes }
      );
      toast.success(`${data.retired.length} jogador(es) removidos do torneio`);
      setRetireOpen(false); setRetireCtx(null);
      await load();
      reloadCompetition?.();
    } catch (e) { toast.error(e.response?.data?.detail || "Erro"); }
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
                  {(g.player_names || []).map((n, i) => {
                    const rid = g.player_reg_ids?.[i];
                    const p = boardByReg[rid];
                    return (
                      <li key={i} className={`text-sm flex items-center justify-between ${p?.retired ? "line-through text-slate-500" : "text-slate-200"}`}>
                        <span><span className="text-slate-500 font-mono text-xs mr-2">{i + 1}.</span>{n}</span>
                        {p?.retired && <Badge className="bg-red-500/20 text-red-300 border border-red-500/40 text-[10px]">OUT</Badge>}
                      </li>
                    );
                  })}
                </ol>
              </div>
            ))}
          </div>
        </section>
      )}

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
                      <MatchRow key={m.match_id} m={m} onSave={saveScore} onRetire={openRetire}
                        teamById={teamById} boardByReg={boardByReg} label={`R${m.round}`} />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {koRounds.length > 0 && (
        <section>
          <h2 className="text-xl font-bold mb-4">Eliminatória</h2>
          <div className="flex gap-6 overflow-x-auto pb-4">
            {koRounds.map(r => (
              <div key={r} className="flex-shrink-0 w-72 space-y-3">
                <div className="text-xs uppercase tracking-widest text-slate-500 font-mono font-bold">
                  {r === koRounds[koRounds.length - 1] && koByRound[r].length === 1 ? "Final" : `Rodada ${r}`}
                </div>
                {koByRound[r].map(m => (
                  <MatchRow key={m.match_id} m={m} onSave={saveScore} onRetire={openRetire}
                    teamById={teamById} boardByReg={boardByReg} />
                ))}
              </div>
            ))}
          </div>
        </section>
      )}

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
                  <tr key={p.registration_id} data-testid={`lb-row-${p.registration_id}`}
                    className={`border-t border-slate-800/60 ${p.retired ? "opacity-40" : ""}`}>
                    <td className="px-4 py-3 font-mono">
                      {p.retired ? <HeartCrack className="w-4 h-4 text-red-400"/>
                        : i === 0 ? <Crown className="w-4 h-4 text-amber-400" />
                          : i < 3 ? <Medal className="w-4 h-4 text-slate-400" />
                            : i + 1}
                    </td>
                    <td className="px-4 py-3 font-semibold flex items-center gap-2">
                      <span className={p.retired ? "line-through" : ""}>{p.name}</span>
                      {p.retired && <Badge className="bg-red-500/20 text-red-300 border border-red-500/40 text-[10px]">
                        {p.retired_by_partner ? "LEVADO PELO PARCEIRO" : p.retired_reason === "estafe" ? "ESTAFE" : p.retired_reason === "outro" ? "OUT" : "CONTUSÃO"}
                      </Badge>}
                    </td>
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

      <RetireDialog open={retireOpen} onOpenChange={setRetireOpen} ctx={retireCtx} onConfirm={doRetire}/>
    </div>
  );
}

function MatchRow({ m, onSave, onRetire, teamById, boardByReg, label }) {
  const [a, setA] = useState(m.score_a);
  const [b, setB] = useState(m.score_b);
  const [winner, setWinner] = useState(m.winner || null);
  useEffect(() => { setA(m.score_a); setB(m.score_b); setWinner(m.winner || null); }, [m.score_a, m.score_b, m.winner]);

  const isTie = Number(a) === Number(b) && Number(a) > 0;
  const needsManualWinner = isTie && !winner;

  const teamPoints = (teamId) => {
    const t = teamById[teamId]; if (!t) return 0;
    return (t.source_registration_ids || [])
      .reduce((sum, rid) => sum + (boardByReg[rid]?.points || 0), 0);
  };
  const suggestByCampaign = () => {
    const pa = teamPoints(m.team_a_id) - Number(a); // exclude current
    const pb = teamPoints(m.team_b_id) - Number(b);
    if (pa === pb) { toast.error("Campanhas empatadas — escolha manualmente"); return; }
    setWinner(pa > pb ? "A" : "B");
    toast.success(`Sugestão: Time ${pa > pb ? "A" : "B"} (mais pontos na campanha)`);
  };

  return (
    <div data-testid={`rot-match-${m.match_id}`} className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden">
      {label && <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 px-3 pt-2 flex justify-between">
        <span>{label}</span>
        <button onClick={() => onRetire(m)} data-testid={`retire-btn-${m.match_id}`}
          className="text-red-400 hover:text-red-300 flex items-center gap-1 text-[10px]">
          <HeartCrack className="w-3 h-3"/> Retirar jogador
        </button>
      </div>}
      <SideRow name={m.team_a_name} score={a} setScore={setA}
        winner={winner === "A"} loser={winner === "B"} tie={isTie}
        onClick={() => isTie && setWinner("A")} clickable={isTie} testid={`side-a-${m.match_id}`}/>
      <div className="h-px bg-slate-800" />
      <SideRow name={m.team_b_name} score={b} setScore={setB}
        winner={winner === "B"} loser={winner === "A"} tie={isTie}
        onClick={() => isTie && setWinner("B")} clickable={isTie} testid={`side-b-${m.match_id}`}/>
      {needsManualWinner && (
        <div className="px-3 py-2 border-t border-amber-500/30 bg-amber-500/10 text-amber-200 text-xs" data-testid={`tie-warn-${m.match_id}`}>
          <div className="flex items-center gap-1.5 mb-1.5"><AlertTriangle className="w-3 h-3"/> Placar empatado — defina o vencedor</div>
          <button onClick={suggestByCampaign} data-testid={`tie-suggest-${m.match_id}`}
            className="inline-flex items-center gap-1 text-emerald-300 hover:text-emerald-200 underline text-[11px]">
            <Sparkles className="w-3 h-3"/> Sugerir pela melhor campanha
          </button>
        </div>
      )}
      {!label && (
        <button onClick={() => onRetire(m)} data-testid={`retire-btn-${m.match_id}`}
          className="w-full px-3 py-1.5 border-t border-slate-800 text-red-400 hover:bg-red-950/30 text-[11px] flex items-center justify-center gap-1">
          <HeartCrack className="w-3 h-3"/> Retirar jogador
        </button>
      )}
      <div className="p-2 border-t border-slate-800 bg-slate-900">
        <Button size="sm" onClick={() => onSave(m, a, b, winner)}
          disabled={needsManualWinner} data-testid={`rot-save-${m.match_id}`}
          className="w-full h-8 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold disabled:opacity-40">
          <Save className="w-3 h-3 mr-1" /> {needsManualWinner ? "Defina o vencedor" : "Salvar placar"}
        </Button>
      </div>
    </div>
  );
}

const SideRow = ({ name, score, setScore, winner, loser, tie, onClick, clickable, testid }) => (
  <div onClick={onClick} data-testid={testid}
    className={`flex justify-between items-center px-3 py-2 ${winner ? "bg-emerald-500/10" : loser ? "bg-slate-950/50" : ""} ${clickable ? "cursor-pointer hover:bg-slate-800/60" : ""}`}>
    <span className={`text-sm truncate flex-1 ${winner ? "text-emerald-300 font-semibold" : loser ? "text-slate-500" : "text-slate-300"}`}>
      {tie && !winner && !loser && <span className="text-amber-400 mr-1">◉</span>}
      {name}
    </span>
    <Input type="number" value={score} onChange={e => setScore(e.target.value)} onClick={e => e.stopPropagation()}
      className="w-14 h-8 bg-slate-800 border-slate-700 text-slate-100 text-center font-mono" />
  </div>
);

function RetireDialog({ open, onOpenChange, ctx, onConfirm }) {
  const [reg, setReg] = useState("");
  const [reason, setReason] = useState("contusao");
  const [notes, setNotes] = useState("");
  useEffect(() => { if (open) { setReg(""); setReason("contusao"); setNotes(""); } }, [open]);
  if (!ctx) return null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-slate-900 border-slate-800 text-slate-100 max-w-md" data-testid="retire-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><HeartCrack className="w-5 h-5 text-red-400"/> Retirar jogador</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <p className="text-sm text-slate-400">
            O jogador será desclassificado e o parceiro de dupla desta partida também sai do torneio.
          </p>
          <div>
            <Label>Jogador que se retira</Label>
            <Select value={reg} onValueChange={setReg}>
              <SelectTrigger data-testid="retire-player-select" className="bg-slate-800 border-slate-700"><SelectValue placeholder="Selecione..."/></SelectTrigger>
              <SelectContent className="bg-slate-900 border-slate-800 text-slate-100">
                {ctx.players.map(p => (
                  <SelectItem key={p.reg_id} value={p.reg_id}>{p.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Motivo</Label>
            <RadioGroup value={reason} onValueChange={setReason} className="flex gap-3 mt-2">
              {[
                { v: "contusao", l: "Contusão" },
                { v: "estafe", l: "Estafe" },
                { v: "outro", l: "Outro" },
              ].map(o => (
                <label key={o.v} className="flex items-center gap-1.5 text-sm cursor-pointer">
                  <RadioGroupItem value={o.v} data-testid={`retire-reason-${o.v}`}/>
                  {o.l}
                </label>
              ))}
            </RadioGroup>
          </div>
          <div>
            <Label>Observações (opcional)</Label>
            <Input value={notes} onChange={e => setNotes(e.target.value)} data-testid="retire-notes"
              className="bg-slate-800 border-slate-700"/>
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline" className="border-slate-700 hover:bg-slate-800">
            Cancelar
          </Button>
          <Button onClick={() => onConfirm(reg, reason, notes)} disabled={!reg}
            data-testid="retire-confirm"
            className="bg-red-500 hover:bg-red-400 text-slate-950 font-bold">
            Confirmar retirada
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
