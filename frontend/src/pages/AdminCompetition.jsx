import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Shuffle, Trophy, Loader2, Users, Save, Radio, QrCode, Pencil, Download, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";

export default function AdminCompetition() {
  const { id } = useParams();
  const [comp, setComp] = useState(null);
  const [types, setTypes] = useState([]);
  const [regs, setRegs] = useState([]);
  const [teams, setTeams] = useState([]);
  const [matches, setMatches] = useState([]);
  const [busy, setBusy] = useState(false);
  const [shuffling, setShuffling] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const bracketRef = useRef(null);

  const load = async () => {
    const [{data:c}, {data:r}, {data:t}, {data:m}, {data:ts}] = await Promise.all([
      api.get(`/competitions/${id}`),
      api.get(`/competitions/${id}/registrations`),
      api.get(`/competitions/${id}/teams`),
      api.get(`/competitions/${id}/matches`),
      api.get(`/competition-types`),
    ]);
    setComp(c); setRegs(r); setTeams(t); setMatches(m); setTypes(ts);
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

  const saveEdit = async (patch) => {
    try {
      await api.put(`/competitions/${id}`, patch);
      toast.success("Torneio atualizado");
      setEditOpen(false);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Erro"); }
  };

  const downloadBracket = async () => {
    if (!bracketRef.current) return;
    setDownloading(true);
    try {
      const { default: html2canvas } = await import("html2canvas");
      const canvas = await html2canvas(bracketRef.current, {
        backgroundColor: "#0B0F17",
        scale: 2, useCORS: true,
      });
      const link = document.createElement("a");
      link.download = `chaveamento-${comp.title.replace(/\s+/g, "-").toLowerCase()}.png`;
      link.href = canvas.toDataURL("image/png");
      link.click();
      toast.success("Chaveamento baixado!");
    } catch (e) { toast.error("Erro ao gerar imagem"); }
    finally { setDownloading(false); }
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
        <div className="flex gap-2 flex-wrap">
          <Button onClick={()=>setEditOpen(true)} data-testid="edit-comp-btn"
            className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold">
            <Pencil className="w-4 h-4 mr-1"/> Editar torneio
          </Button>
          <Link to={`/live/sorteio/${id}`}>
            <Button data-testid="live-sorteio-btn" className="bg-purple-500 hover:bg-purple-400 text-slate-950 font-semibold">
              <Radio className="w-4 h-4 mr-1"/> Sorteio ao Vivo
            </Button>
          </Link>
          <Link to="/admin/checkin">
            <Button data-testid="checkin-nav-btn" variant="outline" className="border-slate-700 hover:bg-slate-800">
              <QrCode className="w-4 h-4 mr-1"/> Check-in
            </Button>
          </Link>
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

      <EditCompetitionDialog open={editOpen} onOpenChange={setEditOpen} comp={comp} types={types} onSave={saveEdit} />

      {/* Registrations */}
      <section className="mb-10">
        <div className="flex items-center gap-2 mb-4">
          <Users className="w-5 h-5 text-emerald-400"/>
          <h2 className="text-xl font-bold">Inscritos ({regs.length})</h2>
        </div>
        <div className="grid md:grid-cols-2 gap-3">
          {regs.map(r => (
            <RegRow key={r.registration_id} r={r} onChange={load} />
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
                <div className="text-xs text-emerald-400 font-mono uppercase mb-2">Time</div>
                <div className="flex items-center gap-3">
                  <div className="flex -space-x-2">
                    {(t.players || []).map((p, i) => (
                      <Avatar key={i} className="w-10 h-10 border-2 border-slate-900">
                        <AvatarImage src={t.players_avatars?.[i]} className="object-cover"/>
                        <AvatarFallback className="bg-emerald-500/20 text-emerald-300 text-xs font-bold">{p?.[0]}</AvatarFallback>
                      </Avatar>
                    ))}
                  </div>
                  <div className="font-semibold text-sm">{t.name}</div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Bracket */}
      {matches.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
            <h2 className="text-xl font-bold">Chaveamento</h2>
            <Button onClick={downloadBracket} disabled={downloading} data-testid="download-bracket-btn"
              className="bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold">
              {downloading ? <Loader2 className="w-4 h-4 animate-spin"/> : <><Download className="w-4 h-4 mr-1"/> Baixar imagem</>}
            </Button>
          </div>
          <div ref={bracketRef} className="bg-[#0B0F17] p-6 rounded-2xl">
            <div className="text-center mb-4">
              <div className="text-xs font-mono uppercase tracking-widest text-emerald-400 mb-1">ArenaHub · Chaveamento oficial</div>
              <div className="text-xl font-extrabold">{comp.title}</div>
              <div className="text-xs text-slate-500">#{comp.type_name?.replace(/\s+/g, "")}</div>
            </div>
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
          </div>
        </section>
      )}
    </div>
  );
}

function RegRow({ r, onChange }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    user_name: r.user_name, user_email: r.user_email,
    mode: r.mode, partner_name: r.partner_name || "",
    partner_email: r.partner_email || "", phone: r.phone || "",
    payment_status: r.payment_status, checked_in: r.checked_in,
  });
  const save = async () => {
    try {
      await api.put(`/admin/registrations/${r.registration_id}`, form);
      toast.success("Inscrição atualizada");
      setOpen(false); onChange();
    } catch (e) { toast.error(e.response?.data?.detail || "Erro"); }
  };
  const del = async () => {
    if (!confirm("Excluir esta inscrição?")) return;
    try {
      await api.delete(`/admin/registrations/${r.registration_id}`);
      toast.success("Inscrição excluída"); onChange();
    } catch (e) { toast.error("Erro"); }
  };
  return (
    <div data-testid={`admin-reg-${r.registration_id}`}
      className="bg-slate-900/70 border border-slate-800 rounded-xl p-4">
      <div className="flex justify-between items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="font-semibold truncate">{r.user_name}</div>
          <div className="text-xs text-slate-500 truncate">{r.user_email} · {r.phone}</div>
          <div className="text-xs text-slate-400 mt-1">
            {r.mode === "individual" ? "Individual (para sorteio)" : `Dupla com ${r.partner_name || "?"}`}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <Badge className={`h-fit border ${
            (r.payment_status === "paid" || r.payment_status === "free")
              ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
              : r.payment_status === "refunded"
                ? "bg-purple-500/20 text-purple-300 border-purple-500/30"
                : "bg-amber-500/20 text-amber-300 border-amber-500/30"}`}>
            {r.payment_status}
          </Badge>
          {r.checked_in && <Badge className="bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 text-[10px]">CHECK-IN OK</Badge>}
        </div>
      </div>
      <div className="mt-3 flex gap-2">
        <Button size="sm" variant="outline" onClick={()=>setOpen(true)} data-testid={`edit-reg-${r.registration_id}`}
          className="border-slate-700 hover:bg-slate-800"><Pencil className="w-3 h-3 mr-1"/> Editar</Button>
        <Button size="sm" variant="outline" onClick={del} data-testid={`del-reg-${r.registration_id}`}
          className="border-red-800/40 text-red-300 hover:bg-red-950/40"><Trash2 className="w-3 h-3"/></Button>
      </div>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-slate-900 border-slate-800 text-slate-100">
          <DialogHeader><DialogTitle>Editar inscrição</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2"><Label>Nome</Label>
              <Input value={form.user_name} onChange={e=>setForm(f=>({...f, user_name:e.target.value}))} className="bg-slate-800 border-slate-700"/></div>
            <div className="col-span-2"><Label>E-mail</Label>
              <Input value={form.user_email} onChange={e=>setForm(f=>({...f, user_email:e.target.value}))} className="bg-slate-800 border-slate-700"/></div>
            <div><Label>Modalidade</Label>
              <Select value={form.mode} onValueChange={v=>setForm(f=>({...f, mode:v}))}>
                <SelectTrigger className="bg-slate-800 border-slate-700"><SelectValue/></SelectTrigger>
                <SelectContent className="bg-slate-900 border-slate-800 text-slate-100">
                  <SelectItem value="individual">Individual</SelectItem>
                  <SelectItem value="dupla">Dupla</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div><Label>Status pagamento</Label>
              <Select value={form.payment_status} onValueChange={v=>setForm(f=>({...f, payment_status:v}))}>
                <SelectTrigger className="bg-slate-800 border-slate-700"><SelectValue/></SelectTrigger>
                <SelectContent className="bg-slate-900 border-slate-800 text-slate-100">
                  <SelectItem value="free">free</SelectItem>
                  <SelectItem value="paid">paid</SelectItem>
                  <SelectItem value="pending">pending</SelectItem>
                  <SelectItem value="refunded">refunded</SelectItem>
                  <SelectItem value="failed">failed</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div><Label>Parceiro (nome)</Label>
              <Input value={form.partner_name} onChange={e=>setForm(f=>({...f, partner_name:e.target.value}))} className="bg-slate-800 border-slate-700"/></div>
            <div><Label>Parceiro (e-mail)</Label>
              <Input value={form.partner_email} onChange={e=>setForm(f=>({...f, partner_email:e.target.value}))} className="bg-slate-800 border-slate-700"/></div>
            <div className="col-span-2"><Label>Telefone</Label>
              <Input value={form.phone} onChange={e=>setForm(f=>({...f, phone:e.target.value}))} className="bg-slate-800 border-slate-700"/></div>
          </div>
          <DialogFooter>
            <Button onClick={save} data-testid={`save-reg-${r.registration_id}`}
              className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold">Salvar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function EditCompetitionDialog({ open, onOpenChange, comp, types, onSave }) {
  const [form, setForm] = useState({});
  useEffect(() => {
    if (comp) setForm({
      title: comp.title, type_id: comp.type_id, description: comp.description || "",
      registration_start: comp.registration_start, registration_end: comp.registration_end,
      start_date: comp.start_date, end_date: comp.end_date, prize: comp.prize,
      fee: comp.fee, max_slots: comp.max_slots, location: comp.location || "",
    });
  }, [comp]);
  const set = (k, v) => setForm(f => ({...f, [k]: v}));
  if (!comp) return null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-slate-900 border-slate-800 text-slate-100 max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader><DialogTitle>Editar torneio</DialogTitle></DialogHeader>
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2"><Label>Título</Label>
            <Input data-testid="edit-title" value={form.title || ""} onChange={e=>set("title", e.target.value)} className="bg-slate-800 border-slate-700"/></div>
          <div className="col-span-2"><Label>Tipo</Label>
            <Select value={form.type_id} onValueChange={v=>set("type_id", v)}>
              <SelectTrigger data-testid="edit-type" className="bg-slate-800 border-slate-700"><SelectValue/></SelectTrigger>
              <SelectContent className="bg-slate-900 border-slate-800 text-slate-100">
                {types.map(t => <SelectItem key={t.type_id} value={t.type_id}>{t.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="col-span-2"><Label>Descrição</Label>
            <Textarea data-testid="edit-desc" value={form.description || ""} onChange={e=>set("description", e.target.value)} className="bg-slate-800 border-slate-700"/></div>
          <div><Label>Início inscrições</Label>
            <Input type="date" data-testid="edit-reg-start" value={form.registration_start || ""} onChange={e=>set("registration_start", e.target.value)} className="bg-slate-800 border-slate-700"/></div>
          <div><Label>Fim inscrições</Label>
            <Input type="date" data-testid="edit-reg-end" value={form.registration_end || ""} onChange={e=>set("registration_end", e.target.value)} className="bg-slate-800 border-slate-700"/></div>
          <div><Label>Início torneio</Label>
            <Input type="date" data-testid="edit-start" value={form.start_date || ""} onChange={e=>set("start_date", e.target.value)} className="bg-slate-800 border-slate-700"/></div>
          <div><Label>Fim torneio</Label>
            <Input type="date" data-testid="edit-end" value={form.end_date || ""} onChange={e=>set("end_date", e.target.value)} className="bg-slate-800 border-slate-700"/></div>
          <div className="col-span-2"><Label>Premiação</Label>
            <Input data-testid="edit-prize" value={form.prize || ""} onChange={e=>set("prize", e.target.value)} className="bg-slate-800 border-slate-700"/></div>
          <div><Label>Valor inscrição (R$)</Label>
            <Input type="number" step="0.01" data-testid="edit-fee" value={form.fee ?? 0} onChange={e=>set("fee", e.target.value)} className="bg-slate-800 border-slate-700"/></div>
          <div><Label>Vagas máximas</Label>
            <Input type="number" data-testid="edit-slots" value={form.max_slots ?? 16} onChange={e=>set("max_slots", e.target.value)} className="bg-slate-800 border-slate-700"/></div>
          <div className="col-span-2"><Label>Local</Label>
            <Input data-testid="edit-location" value={form.location || ""} onChange={e=>set("location", e.target.value)} className="bg-slate-800 border-slate-700"/></div>
        </div>
        <DialogFooter>
          <Button onClick={()=>onSave({...form, fee: Number(form.fee), max_slots: Number(form.max_slots)})}
            data-testid="save-edit-btn" className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold">
            Salvar alterações
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
