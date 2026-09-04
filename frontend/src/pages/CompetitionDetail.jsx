import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Trophy, Calendar, MapPin, Users, DollarSign, Loader2, MessageCircle } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { ShareButtons } from "@/components/ShareButtons";

export default function CompetitionDetail() {
  const { id } = useParams();
  const { user, login } = useAuth();
  const [comp, setComp] = useState(null);
  const [teams, setTeams] = useState([]);
  const [matches, setMatches] = useState([]);
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState("individual");
  const [partnerName, setPartner] = useState("");
  const [partnerEmail, setPartnerEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = async () => {
    const [{data: c}, {data: t}, {data: m}] = await Promise.all([
      api.get(`/competitions/${id}`),
      api.get(`/competitions/${id}/teams`),
      api.get(`/competitions/${id}/matches`),
    ]);
    setComp(c); setTeams(t); setMatches(m);
  };

  useEffect(() => { load(); }, [id]);

  if (!comp) return <div className="p-10 text-slate-400">Carregando...</div>;

  const register = async () => {
    if (!user) { login(); return; }
    setSubmitting(true);
    try {
      const { data } = await api.post("/registrations", {
        competition_id: id, mode, partner_name: partnerName, partner_email: partnerEmail,
        phone, origin_url: window.location.origin,
      });
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
      } else {
        toast.success("Inscrição confirmada! Confira seu e-mail.");
        setOpen(false);
        load();
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || "Erro ao inscrever");
    } finally { setSubmitting(false); }
  };

  const rounds = matches.reduce((acc, m) => {
    (acc[m.round] = acc[m.round] || []).push(m);
    return acc;
  }, {});
  const roundKeys = Object.keys(rounds).map(Number).sort((a,b)=>a-b);

  const shareMatch = (m, c) => {
    const winnerName = m.winner === "A" ? m.team_a_name : m.team_b_name;
    const text = `🏆 ${c.title}\n${m.team_a_name} ${m.score_a} x ${m.score_b} ${m.team_b_name}\nVencedor: ${winnerName}`;
    const url = `${window.location.origin}/competicoes/${c.competition_id}`;
    if (navigator.share) {
      navigator.share({ text, url }).catch(()=>{});
    } else {
      window.open(`https://wa.me/?text=${encodeURIComponent(text + "\n\n" + url)}`, "_blank", "noopener");
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      <div className="grid lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2">
          <Badge className="mb-3 bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">{comp.type_name}</Badge>
          <h1 className="text-3xl sm:text-4xl font-extrabold mb-3" data-testid="detail-title">{comp.title}</h1>
          <p className="text-slate-400 mb-4">{comp.description || "Cadastre-se e prepare-se para a disputa."}</p>
          <div className="mb-6">
            <ShareButtons
              text={`🏆 ${comp.title} · ${comp.type_name} · ${comp.start_date}${comp.location ? " · " + comp.location : ""}`}
              dataTestidPrefix="share-comp"
            />
          </div>

          <div className="grid sm:grid-cols-2 gap-4 mb-8">
            <InfoCard icon={Calendar} label="Inscrições" value={`${comp.registration_start} → ${comp.registration_end}`} />
            <InfoCard icon={Calendar} label="Torneio" value={`${comp.start_date} → ${comp.end_date}`} />
            <InfoCard icon={MapPin} label="Local" value={comp.location || "A definir"} />
            <InfoCard icon={Trophy} label="Premiação" value={comp.prize} accent="amber" />
            <InfoCard icon={Users} label="Vagas" value={`${comp.registered_count}/${comp.max_slots}`} accent="cyan" />
            <InfoCard icon={DollarSign} label="Inscrição" value={comp.fee > 0 ? `R$ ${comp.fee.toFixed(2)}` : "Gratuito"} accent={comp.fee > 0 ? "amber" : "emerald"} />
          </div>

          {teams.length > 0 && (
            <div className="mb-10">
              <h2 className="text-2xl font-bold mb-4">Duplas sorteadas</h2>
              <div className="grid sm:grid-cols-2 gap-3">
                {teams.map(t => (
                  <div key={t.team_id} data-testid={`team-${t.team_id}`} className="bg-slate-900/60 border border-slate-800 rounded-xl p-4">
                    <div className="text-xs text-emerald-400 font-mono uppercase mb-1">Dupla</div>
                    <div className="font-semibold">{t.name}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {matches.length > 0 && (
            <div>
              <h2 className="text-2xl font-bold mb-4">Chaveamento</h2>
              <div className="flex gap-6 overflow-x-auto pb-4">
                {roundKeys.map(r => (
                  <div key={r} className="flex-shrink-0 w-64 space-y-4">
                    <div className="text-xs uppercase tracking-widest text-slate-500 font-mono font-semibold">
                      {r === roundKeys[roundKeys.length-1] ? "Final" : `Rodada ${r}`}
                    </div>
                    {rounds[r].map(m => (
                      <div key={m.match_id} data-testid={`match-${m.match_id}`}
                        className="bg-slate-900/70 border border-slate-800 rounded-xl overflow-hidden">
                        <MatchLine name={m.team_a_name} score={m.score_a} winner={m.winner === "A"} />
                        <div className="h-px bg-slate-800" />
                        <MatchLine name={m.team_b_name} score={m.score_b} winner={m.winner === "B"} />
                        {m.winner && (
                          <button onClick={() => shareMatch(m, comp)} data-testid={`share-match-${m.match_id}`}
                            className="w-full flex items-center justify-center gap-1 text-xs py-2 border-t border-slate-800 text-slate-400 hover:text-emerald-400 hover:bg-slate-800/40 transition-colors">
                            <MessageCircle className="w-3 h-3"/> Compartilhar placar
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="lg:col-span-1">
          <div className="sticky top-24 bg-slate-900/80 border border-slate-800 rounded-2xl p-6">
            <div className="text-3xl font-extrabold mb-1">
              {comp.fee > 0 ? `R$ ${comp.fee.toFixed(2)}` : <span className="text-emerald-400">Gratuito</span>}
            </div>
            <div className="text-slate-400 text-sm mb-6">Inscrição {comp.fee > 0 ? "com pagamento seguro" : "sem custos"}</div>

            <Dialog open={open} onOpenChange={setOpen}>
              <DialogTrigger asChild>
                <Button data-testid="open-register-btn" className="w-full bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold rounded-xl h-12">
                  Inscrever-se agora
                </Button>
              </DialogTrigger>
              <DialogContent className="bg-slate-900 border-slate-800 text-slate-100 max-w-md">
                <DialogHeader>
                  <DialogTitle>Inscrição em {comp.title}</DialogTitle>
                </DialogHeader>
                <div className="space-y-4">
                  <div>
                    <Label className="mb-2 block">Modalidade</Label>
                    <RadioGroup value={mode} onValueChange={setMode}>
                      <div className="flex items-center gap-2 p-3 rounded-lg border border-slate-800 hover:border-emerald-500/40 cursor-pointer"
                        onClick={()=>setMode("individual")}>
                        <RadioGroupItem value="individual" id="ind" data-testid="mode-individual" />
                        <Label htmlFor="ind" className="cursor-pointer flex-1">
                          <div className="font-medium">Individual (sorteio)</div>
                          <div className="text-xs text-slate-400">Você será sorteado com outro atleta</div>
                        </Label>
                      </div>
                      <div className="flex items-center gap-2 p-3 rounded-lg border border-slate-800 hover:border-emerald-500/40 cursor-pointer"
                        onClick={()=>setMode("dupla")}>
                        <RadioGroupItem value="dupla" id="dup" data-testid="mode-dupla" />
                        <Label htmlFor="dup" className="cursor-pointer flex-1">
                          <div className="font-medium">Dupla confirmada</div>
                          <div className="text-xs text-slate-400">Já tenho um parceiro(a)</div>
                        </Label>
                      </div>
                    </RadioGroup>
                  </div>

                  {mode === "dupla" && (
                    <>
                      <div>
                        <Label htmlFor="pn">Nome do parceiro(a)</Label>
                        <Input id="pn" data-testid="partner-name" value={partnerName} onChange={e=>setPartner(e.target.value)}
                          className="bg-slate-800 border-slate-700 text-slate-100" />
                      </div>
                      <div>
                        <Label htmlFor="pe">Email do parceiro(a)</Label>
                        <Input id="pe" data-testid="partner-email" value={partnerEmail} onChange={e=>setPartnerEmail(e.target.value)}
                          className="bg-slate-800 border-slate-700 text-slate-100" />
                      </div>
                    </>
                  )}
                  <div>
                    <Label htmlFor="ph">Telefone (WhatsApp)</Label>
                    <Input id="ph" data-testid="phone" value={phone} onChange={e=>setPhone(e.target.value)}
                      className="bg-slate-800 border-slate-700 text-slate-100" />
                  </div>
                </div>
                <DialogFooter>
                  <Button onClick={register} disabled={submitting} data-testid="confirm-register-btn"
                    className="w-full bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold">
                    {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : (comp.fee > 0 ? "Ir para pagamento" : "Confirmar inscrição")}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>

            <p className="text-xs text-slate-500 mt-4 text-center">Ao confirmar você receberá um e-mail com os dados da inscrição.</p>
          </div>
        </div>
      </div>
    </div>
  );
}

const InfoCard = ({ icon: Icon, label, value, accent = "slate" }) => (
  <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4">
    <div className="flex items-center gap-2 text-xs uppercase tracking-widest text-slate-500 font-mono mb-1">
      <Icon className={`w-3.5 h-3.5 text-${accent}-400`} /> {label}
    </div>
    <div className={`font-semibold ${accent === "amber" ? "text-amber-300" : accent === "cyan" ? "text-cyan-300" : accent === "emerald" ? "text-emerald-300" : ""}`}>
      {value}
    </div>
  </div>
);

const MatchLine = ({ name, score, winner }) => (
  <div className={`flex justify-between items-center px-4 py-2.5 ${winner ? "bg-emerald-500/10" : ""}`}>
    <span className={`text-sm truncate ${winner ? "text-emerald-300 font-semibold" : "text-slate-300"}`}>{name}</span>
    <span className={`font-mono font-bold text-sm ${winner ? "text-emerald-400" : "text-slate-500"}`}>{score}</span>
  </div>
);
