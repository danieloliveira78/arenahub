import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Trophy, Plus, Trash2, Settings, ExternalLink, DollarSign, Users } from "lucide-react";
import { toast } from "sonner";
import AccessGate from "@/components/AccessGate";

export default function Admin() {
  return (
    <AccessGate>
      <AdminInner />
    </AccessGate>
  );
}

function AdminInner() {
  const [types, setTypes] = useState([]);
  const [comps, setComps] = useState([]);

  const load = async () => {
    const [{data: t}, {data: c}] = await Promise.all([
      api.get("/competition-types"), api.get("/competitions"),
    ]);
    setTypes(t); setComps(c);
  };

  useEffect(() => { load(); }, []);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10" data-testid="admin">
      <div className="mb-8 flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="text-xs font-mono uppercase tracking-widest text-amber-400 mb-2">Painel Administrativo</div>
          <h1 className="text-3xl sm:text-4xl font-extrabold">Gestão de torneios</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to="/admin/usuarios">
            <Button data-testid="go-users-btn" variant="outline" className="border-slate-700 hover:bg-slate-800">
              <Users className="w-4 h-4 mr-1"/> Usuários
            </Button>
          </Link>
          <Link to="/admin/financeiro">
            <Button data-testid="go-finance-btn" variant="outline" className="border-slate-700 hover:bg-slate-800">
              <DollarSign className="w-4 h-4 mr-1"/> Financeiro
            </Button>
          </Link>
        </div>
      </div>

      <Tabs defaultValue="competitions">
        <TabsList className="bg-slate-900 border border-slate-800">
          <TabsTrigger value="competitions" data-testid="tab-competitions">Torneios</TabsTrigger>
          <TabsTrigger value="types" data-testid="tab-types">Tipos de competição</TabsTrigger>
          <TabsTrigger value="stripe" data-testid="tab-stripe">Pagamentos</TabsTrigger>
        </TabsList>

        <TabsContent value="competitions" className="mt-6">
          <CompetitionSection types={types} comps={comps} onChange={load} />
        </TabsContent>

        <TabsContent value="types" className="mt-6">
          <TypeSection types={types} onChange={load} />
        </TabsContent>

        <TabsContent value="stripe" className="mt-6">
          <StripeSection />
        </TabsContent>
      </Tabs>
    </div>
  );
}

const StripeSection = () => (
  <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6 max-w-2xl">
    <div className="flex items-center gap-2 mb-2">
      <Settings className="w-5 h-5 text-emerald-400"/>
      <h3 className="text-lg font-bold">Ativar pagamentos reais (PIX + Cartão)</h3>
    </div>
    <p className="text-slate-400 mb-4 text-sm">
      No modo atual (sandbox), somente o cartão de teste 4242 4242 4242 4242 funciona. Para receber pagamentos reais e liberar o <strong>PIX</strong>, reivindique sua conta Stripe brasileira. Não precisa criar conta nova — é só clicar abaixo e completar o KYC.
    </p>
    <a href="https://dashboard.stripe.com/onboard_sandbox/YWNjdF8xVUJFSGtLOTJORUlFUjhYLDE3ODkxNTEyMjkv100pMMJxjZQ"
       target="_blank" rel="noopener noreferrer">
      <Button data-testid="claim-stripe-btn" className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold">
        Reivindicar conta Stripe <ExternalLink className="w-4 h-4 ml-1"/>
      </Button>
    </a>
    <div className="mt-4 pt-4 border-t border-slate-800 text-xs text-slate-500 space-y-1">
      <div>· Depois de reivindicar, o Emergent troca as chaves automaticamente no próximo deploy.</div>
      <div>· PIX exige conta com KYC aprovado (documento + comprovante de titularidade).</div>
      <div>· Cartão fica ativo imediatamente após reivindicação.</div>
    </div>
  </div>
);

const TypeSection = ({ types, onChange }) => {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(""); const [format, setFormat] = useState("duplas");
  const [description, setDescription] = useState("");

  const create = async () => {
    if (!name) return toast.error("Informe o nome");
    try {
      await api.post("/competition-types", { name, format, description });
      toast.success("Tipo criado");
      setOpen(false); setName(""); setDescription("");
      onChange();
    } catch (e) { toast.error(e.response?.data?.detail || "Erro"); }
  };

  const remove = async (id) => {
    if (!confirm("Excluir este tipo?")) return;
    await api.delete(`/competition-types/${id}`);
    onChange();
  };

  return (
    <div>
      <div className="flex justify-end mb-4">
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button data-testid="new-type-btn" className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold">
              <Plus className="w-4 h-4 mr-1"/> Novo tipo
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-slate-900 border-slate-800 text-slate-100">
            <DialogHeader><DialogTitle>Novo tipo de competição</DialogTitle></DialogHeader>
            <div className="space-y-4">
              <div>
                <Label>Nome</Label>
                <Input data-testid="type-name" value={name} onChange={e=>setName(e.target.value)}
                  className="bg-slate-800 border-slate-700" />
              </div>
              <div>
                <Label>Formato</Label>
                <Select value={format} onValueChange={setFormat}>
                  <SelectTrigger data-testid="type-format" className="bg-slate-800 border-slate-700"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-slate-900 border-slate-800 text-slate-100">
                    <SelectItem value="individual">Individual</SelectItem>
                    <SelectItem value="duplas">Duplas</SelectItem>
                    <SelectItem value="times">Times</SelectItem>
                    <SelectItem value="duplas_rotativas">Duplas rotativas (Rei da Praia)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Descrição</Label>
                <Textarea data-testid="type-description" value={description} onChange={e=>setDescription(e.target.value)}
                  className="bg-slate-800 border-slate-700" />
              </div>
            </div>
            <DialogFooter>
              <Button onClick={create} data-testid="save-type-btn" className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold">Criar</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        {types.map(t => (
          <div key={t.type_id} data-testid={`type-${t.type_id}`} className="bg-slate-900/70 border border-slate-800 rounded-xl p-5">
            <div className="flex justify-between items-start mb-2">
              <h3 className="font-bold">{t.name}</h3>
              <button onClick={()=>remove(t.type_id)} className="text-slate-500 hover:text-red-400"><Trash2 className="w-4 h-4" /></button>
            </div>
            <div className="text-xs text-emerald-400 font-mono uppercase">{t.format}</div>
            {t.description && <p className="text-sm text-slate-400 mt-2">{t.description}</p>}
          </div>
        ))}
      </div>
    </div>
  );
};

const CompetitionSection = ({ types, comps, onChange }) => {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    title: "", type_id: "", description: "", registration_start: "", registration_end: "",
    start_date: "", end_date: "", prize: "", fee: 0, max_slots: 16, location: "",
  });
  const set = (k, v) => setForm(f => ({...f, [k]: v}));

  const create = async () => {
    if (!form.title || !form.type_id) return toast.error("Preencha título e tipo");
    try {
      await api.post("/competitions", { ...form, fee: Number(form.fee), max_slots: Number(form.max_slots) });
      toast.success("Torneio criado");
      setOpen(false);
      setForm({...form, title:"", description:"", prize:"", location:""});
      onChange();
    } catch (e) { toast.error(e.response?.data?.detail || "Erro"); }
  };

  const remove = async (id) => {
    if (!confirm("Excluir este torneio? Todas as inscrições e chaves serão apagadas.")) return;
    await api.delete(`/competitions/${id}`);
    onChange();
  };

  return (
    <div>
      <div className="flex justify-end mb-4">
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button data-testid="new-comp-btn" className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold">
              <Plus className="w-4 h-4 mr-1"/> Novo torneio
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-slate-900 border-slate-800 text-slate-100 max-w-2xl">
            <DialogHeader><DialogTitle>Novo torneio</DialogTitle></DialogHeader>
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <Label>Título</Label>
                <Input data-testid="comp-title" value={form.title} onChange={e=>set("title", e.target.value)} className="bg-slate-800 border-slate-700" />
              </div>
              <div className="col-span-2">
                <Label>Tipo</Label>
                <Select value={form.type_id} onValueChange={v=>set("type_id", v)}>
                  <SelectTrigger data-testid="comp-type" className="bg-slate-800 border-slate-700"><SelectValue placeholder="Selecione..."/></SelectTrigger>
                  <SelectContent className="bg-slate-900 border-slate-800 text-slate-100">
                    {types.map(t => <SelectItem key={t.type_id} value={t.type_id}>{t.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="col-span-2">
                <Label>Descrição</Label>
                <Textarea data-testid="comp-desc" value={form.description} onChange={e=>set("description", e.target.value)} className="bg-slate-800 border-slate-700" />
              </div>
              <div><Label>Início inscrições</Label>
                <Input type="date" data-testid="comp-reg-start" value={form.registration_start} onChange={e=>set("registration_start", e.target.value)} className="bg-slate-800 border-slate-700" /></div>
              <div><Label>Fim inscrições</Label>
                <Input type="date" data-testid="comp-reg-end" value={form.registration_end} onChange={e=>set("registration_end", e.target.value)} className="bg-slate-800 border-slate-700" /></div>
              <div><Label>Início torneio</Label>
                <Input type="date" data-testid="comp-start" value={form.start_date} onChange={e=>set("start_date", e.target.value)} className="bg-slate-800 border-slate-700" /></div>
              <div><Label>Fim torneio</Label>
                <Input type="date" data-testid="comp-end" value={form.end_date} onChange={e=>set("end_date", e.target.value)} className="bg-slate-800 border-slate-700" /></div>
              <div className="col-span-2"><Label>Premiação</Label>
                <Input data-testid="comp-prize" value={form.prize} onChange={e=>set("prize", e.target.value)} className="bg-slate-800 border-slate-700" placeholder="Ex: R$ 5.000 + Troféu" /></div>
              <div><Label>Valor inscrição (R$, 0 = grátis)</Label>
                <Input type="number" step="0.01" data-testid="comp-fee" value={form.fee} onChange={e=>set("fee", e.target.value)} className="bg-slate-800 border-slate-700" /></div>
              <div><Label>Vagas máximas</Label>
                <Input type="number" data-testid="comp-slots" value={form.max_slots} onChange={e=>set("max_slots", e.target.value)} className="bg-slate-800 border-slate-700" /></div>
              <div className="col-span-2"><Label>Local</Label>
                <Input data-testid="comp-location" value={form.location} onChange={e=>set("location", e.target.value)} className="bg-slate-800 border-slate-700" /></div>
            </div>
            <DialogFooter>
              <Button onClick={create} data-testid="save-comp-btn" className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold">Criar torneio</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {comps.length === 0 ? (
        <div className="text-center py-16 border border-dashed border-slate-800 rounded-2xl">
          <Trophy className="w-10 h-10 mx-auto text-slate-600 mb-3" />
          <p className="text-slate-400">Nenhum torneio cadastrado ainda.</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {comps.map(c => (
            <div key={c.competition_id} data-testid={`admin-comp-${c.competition_id}`}
              className="bg-slate-900/70 border border-slate-800 rounded-xl p-5 flex items-center justify-between hover:border-emerald-500/40">
              <div>
                <div className="text-xs text-emerald-400 font-mono uppercase">{c.type_name}</div>
                <h3 className="text-lg font-bold">{c.title}</h3>
                <div className="text-sm text-slate-400">{c.registered_count}/{c.max_slots} inscritos · {c.fee > 0 ? `R$ ${c.fee.toFixed(2)}` : "Grátis"}</div>
              </div>
              <div className="flex items-center gap-2">
                <Link to={`/admin/competicoes/${c.competition_id}`}>
                  <Button variant="outline" size="sm" data-testid={`manage-${c.competition_id}`} className="border-slate-700 hover:bg-slate-800">
                    Gerenciar / Editar
                  </Button>
                </Link>
                <button onClick={()=>remove(c.competition_id)} className="text-slate-500 hover:text-red-400 p-2"><Trash2 className="w-4 h-4" /></button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
