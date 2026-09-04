import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Badge } from "@/components/ui/badge";
import { Trophy, Calendar } from "lucide-react";

export default function Dashboard() {
  const { user } = useAuth();
  const [regs, setRegs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/my-registrations").then(({data}) => setRegs(data)).finally(()=>setLoading(false));
  }, []);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10" data-testid="dashboard">
      <h1 className="text-3xl sm:text-4xl font-extrabold mb-2">Olá, {user?.name?.split(" ")[0]}</h1>
      <p className="text-slate-400 mb-8">Suas inscrições e torneios em um só lugar.</p>

      {loading ? (
        <div className="text-slate-500">Carregando...</div>
      ) : regs.length === 0 ? (
        <div className="text-center py-16 border border-dashed border-slate-800 rounded-2xl">
          <Trophy className="w-10 h-10 mx-auto text-slate-600 mb-3" />
          <p className="text-slate-400 mb-4">Você ainda não se inscreveu em nenhum torneio.</p>
          <Link to="/competicoes" className="text-emerald-400 hover:underline">Ver torneios abertos</Link>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {regs.map(r => (
            <Link key={r.registration_id} to={`/competicoes/${r.competition_id}`} data-testid={`reg-${r.registration_id}`}
              className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5 hover:border-emerald-500/40 transition-colors">
              <div className="flex items-start justify-between mb-2">
                <div>
                  <div className="text-xs uppercase text-emerald-400 font-mono tracking-widest">{r.competition?.type_name}</div>
                  <h3 className="text-lg font-bold">{r.competition?.title}</h3>
                </div>
                <StatusBadge status={r.payment_status} />
              </div>
              <div className="text-sm text-slate-400 flex items-center gap-2 mt-3">
                <Calendar className="w-3.5 h-3.5" /> {r.competition?.start_date}
              </div>
              <div className="text-xs text-slate-500 mt-1">Modalidade: {r.mode === "individual" ? "Individual (aguardando sorteio)" : `Dupla com ${r.partner_name}`}</div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

const StatusBadge = ({ status }) => {
  const map = {
    paid: {label:"Pago", cls:"bg-emerald-500/20 text-emerald-300 border-emerald-500/30"},
    free: {label:"Confirmado", cls:"bg-emerald-500/20 text-emerald-300 border-emerald-500/30"},
    pending: {label:"Pagamento pendente", cls:"bg-amber-500/20 text-amber-300 border-amber-500/30"},
    failed: {label:"Falhou", cls:"bg-red-500/20 text-red-300 border-red-500/30"},
  };
  const s = map[status] || map.pending;
  return <Badge className={`border ${s.cls}`}>{s.label}</Badge>;
};
