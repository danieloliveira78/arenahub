import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Shuffle, Trophy, Loader2, Users, Save } from "lucide-react";
import { toast } from "sonner";

export default function AdminCompetition() {
  const { id } = useParams();
  const [comp, setComp] = useState(null);
  const [regs, setRegs] = useState([]);
  const [teams, setTeams] = useState([]);
  const [matches, setMatches] = useState([]);
  const [busy, setBusy] = useState(false);
  const [shuffling, setShuffling] = useState(false);

  const load = async () => {
    const [{data:c}, {data:r}, {data:t}, {data:m}] = await Promise.all([
      api.get(`/competitions/${id}`),
      api.get(`/competitions/${id}/registrations`),
      api.get(`/competitions/${id}/teams`),
      api.get(`/competitions/${id}/matches`),
    ]);
    setComp(c); setRegs(r); setTeams(t); setMatches(m);
  };

  useEffect(() => { load(); }, [id]);

  const doDraw = async () => {
    setShuffling(true);
    try {
      await api.post(`/competitions/${id}/draw`);
      toast.success("Sorteio realizado!");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Erro no sorteio"); }
    finally { setTimeout(() => setShuffling(false), 700); }
  };

  const genBracket = async () => {
    setBusy(true);
    try {
      await api.post(`/competitions/${id}/bracket`);
      toast.success("Chaveamento gerado!");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Erro"); }
    finally { setBusy(false); }
  };

  const saveScore = async (m, score_a, score_b) => {
    try {
      await api.put(`/matches/${m.match_id}`, { score_a: Number(score_a), score_b: Number(score_b) });
      toast.success("Placar salvo");
      load();
    } catch (e) { toast.error("Erro ao salvar"); }
  };

  if (!comp) return <div className="p-10 text-slate-400">Carregando...</div>;

  const rounds = matches.reduce((acc, m) => { (acc[m.round]=acc[m.round]||[]).push(m); return acc; }, {});
  const roundKeys = Object.keys(rounds).map(Number).sort((a,b)=>a-b);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      <div className="flex items-start justify-between flex-wrap gap-4 mb-8">
        <div>
          <div className="text-xs font-mono uppercase tracking-widest text-amber-400 mb-1">Painel do torneio</div>
          <h1 className="text-3xl font-extrabold">{comp.title}</h1>
          <div className="text-slate-400 text-sm mt-1">{comp.type_name} · {regs.length} inscritos</div>
        </div>
        <div className="flex gap-2">
          <Button onClick={doDraw} data-testid="draw-btn"
            className={`bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold ${shuffling ? "shuffle-anim":""}`}>
            <Shuffle className="w-4 h-4 mr-1"/> Sortear duplas
          </Button>
          <Button onClick={genBracket} disabled={busy || teams.length < 2} data-testid="bracket-btn"
            className="bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold">
            {busy ? <Loader2 className="w-4 h-4 animate-spin"/> : <Trophy className="w-4 h-4 mr-1"/>} Gerar chaveamento
          </Button>
        </div>
      </div>

      {/* Registrations */}
      <section className="mb-10">
        <div className="flex items-center gap-2 mb-4">
          <Users className="w-5 h-5 text-emerald-400"/>
          <h2 className="text-xl font-bold">Inscritos ({regs.length})</h2>
        </div>
        <div className="grid md:grid-cols-2 gap-3">
          {regs.map(r => (
            <div key={r.registration_id} data-testid={`admin-reg-${r.registration_id}`}
              className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 flex justify-between">
              <div>
                <div className="font-semibold">{r.user_name}</div>
                <div className="text-xs text-slate-500">{r.user_email} · {r.phone}</div>
                <div className="text-xs text-slate-400 mt-1">
                  {r.mode === "individual" ? "Individual (para sorteio)" : `Dupla com ${r.partner_name || "?"}`}
                </div>
              </div>
              <Badge className={`h-fit border ${
                (r.payment_status === "paid" || r.payment_status === "free")
                  ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
                  : "bg-amber-500/20 text-amber-300 border-amber-500/30"}`}>
                {r.payment_status}
              </Badge>
            </div>
          ))}
        </div>
      </section>

      {/* Teams */}
      {teams.length > 0 && (
        <section className="mb-10">
          <h2 className="text-xl font-bold mb-4">Duplas / Times sorteados</h2>
          <div className="grid md:grid-cols-3 gap-3">
            {teams.map(t => (
              <div key={t.team_id} className="bg-slate-900/70 border border-slate-800 rounded-xl p-4">
                <div className="text-xs text-emerald-400 font-mono uppercase">Time</div>
                <div className="font-semibold">{t.name}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Bracket */}
      {matches.length > 0 && (
        <section>
          <h2 className="text-xl font-bold mb-4">Chaveamento</h2>
          <div className="flex gap-6 overflow-x-auto pb-4">
            {roundKeys.map(r => (
              <div key={r} className="flex-shrink-0 w-72 space-y-3">
                <div className="text-xs uppercase tracking-widest text-slate-500 font-mono font-bold">
                  {r === roundKeys[roundKeys.length-1] ? "Final" : `Rodada ${r}`}
                </div>
                {rounds[r].map(m => <EditableMatch key={m.match_id} m={m} onSave={saveScore} />)}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function EditableMatch({ m, onSave }) {
  const [a, setA] = useState(m.score_a);
  const [b, setB] = useState(m.score_b);
  useEffect(()=>{ setA(m.score_a); setB(m.score_b); }, [m.score_a, m.score_b]);

  const disabled = !m.team_a_id || !m.team_b_id || m.team_a_name === "TBD" || m.team_b_name === "TBD" || m.team_a_name === "BYE" || m.team_b_name === "BYE";

  return (
    <div data-testid={`admin-match-${m.match_id}`} className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden">
      <Row name={m.team_a_name} score={a} setScore={setA} winner={m.winner === "A"} disabled={disabled} />
      <div className="h-px bg-slate-800" />
      <Row name={m.team_b_name} score={b} setScore={setB} winner={m.winner === "B"} disabled={disabled} />
      <div className="p-2 border-t border-slate-800 bg-slate-900">
        <Button size="sm" onClick={() => onSave(m, a, b)} disabled={disabled} data-testid={`save-match-${m.match_id}`}
          className="w-full h-8 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold">
          <Save className="w-3 h-3 mr-1"/> Salvar placar
        </Button>
      </div>
    </div>
  );
}

const Row = ({ name, score, setScore, winner, disabled }) => (
  <div className={`flex justify-between items-center px-3 py-2 ${winner ? "bg-emerald-500/10" : ""}`}>
    <span className={`text-sm truncate flex-1 ${winner ? "text-emerald-300 font-semibold" : "text-slate-300"}`}>{name}</span>
    <Input type="number" value={score} onChange={e=>setScore(e.target.value)} disabled={disabled}
      className="w-14 h-8 bg-slate-800 border-slate-700 text-slate-100 text-center font-mono" />
  </div>
);
