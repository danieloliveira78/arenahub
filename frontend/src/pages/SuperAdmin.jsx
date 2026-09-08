import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Users, TrendingUp, XCircle, Clock, DollarSign } from "lucide-react";

const brl = (v) => `R$ ${Number(v || 0).toFixed(2).replace(".", ",")}`;

export default function SuperAdmin() {
  const [stats, setStats] = useState(null);
  const [tenants, setTenants] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.get("/platform/stats"), api.get("/platform/tenants")])
      .then(([{data: s}, {data: t}]) => { setStats(s); setTenants(t); })
      .finally(()=>setLoading(false));
  }, []);

  if (loading) return <div className="p-10 text-slate-400">Carregando...</div>;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10" data-testid="super-admin">
      <div className="text-xs font-mono uppercase tracking-widest text-purple-400 mb-2">Plataforma · Super Admin</div>
      <h1 className="text-3xl sm:text-4xl font-extrabold mb-8">Painel da plataforma</h1>

      <div className="grid sm:grid-cols-4 gap-4 mb-10">
        <StatCard icon={Users} label="Clientes" value={stats.totals.tenants} color="cyan"/>
        <StatCard icon={TrendingUp} label="Ativos + Trial" value={stats.totals.active} color="emerald"/>
        <StatCard icon={Clock} label="Pendentes" value={stats.totals.past_due} color="amber"/>
        <StatCard icon={XCircle} label="Cancelados" value={stats.totals.canceled} color="red"/>
      </div>

      <div className="grid sm:grid-cols-2 gap-4 mb-10">
        <MoneyCard label="MRR (Receita Recorrente Mensal)" value={brl(stats.mrr)} color="emerald"/>
        <MoneyCard label="Receita de Inscrições (total)" value={brl(stats.total_tournament_revenue)} color="cyan"/>
      </div>

      <h2 className="text-xl font-bold mb-4">Clientes ({tenants.length})</h2>
      <div className="bg-slate-900/70 border border-slate-800 rounded-2xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-900 text-xs uppercase tracking-widest text-slate-500 font-mono">
            <tr>
              <th className="text-left px-4 py-3">Organização</th>
              <th className="text-left px-4 py-3">Owner</th>
              <th className="text-center px-4 py-3">Status</th>
              <th className="text-center px-4 py-3">Plano</th>
              <th className="text-right px-4 py-3">Torneios</th>
              <th className="text-right px-4 py-3">Usuários</th>
            </tr>
          </thead>
          <tbody>
            {tenants.map((t) => (
              <tr key={t.tenant_id} data-testid={`tenant-${t.tenant_id}`} className="border-t border-slate-800/60">
                <td className="px-4 py-3">
                  <div className="font-semibold">{t.name}</div>
                  <div className="text-xs text-slate-500">{t.slug}</div>
                </td>
                <td className="px-4 py-3 text-slate-300 text-xs">{t.owner?.email}</td>
                <td className="px-4 py-3 text-center"><StatusPill status={t.subscription_status}/></td>
                <td className="px-4 py-3 text-center text-slate-400 text-xs">{t.plan_lookup_key || t.plan || "—"}</td>
                <td className="px-4 py-3 text-right font-mono">{t.competitions_count}</td>
                <td className="px-4 py-3 text-right font-mono">{t.users_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const StatCard = ({ icon: Icon, label, value, color }) => (
  <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5">
    <div className="flex items-center gap-2 text-xs uppercase tracking-widest text-slate-500 font-mono mb-1">
      <Icon className={`w-4 h-4 text-${color}-400`}/> {label}
    </div>
    <div className={`text-3xl font-extrabold text-${color}-300`}>{value}</div>
  </div>
);

const MoneyCard = ({ label, value, color }) => (
  <div className="bg-gradient-to-br from-slate-900 via-slate-900 to-slate-800 border border-slate-800 rounded-2xl p-6">
    <div className="flex items-center gap-2 text-xs uppercase tracking-widest text-slate-500 font-mono mb-1">
      <DollarSign className={`w-4 h-4 text-${color}-400`}/> {label}
    </div>
    <div className={`text-4xl font-extrabold text-${color}-300`}>{value}</div>
  </div>
);

const StatusPill = ({ status }) => {
  const map = {
    active: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
    trialing: "bg-cyan-500/20 text-cyan-300 border-cyan-500/40",
    past_due: "bg-amber-500/20 text-amber-300 border-amber-500/40",
    canceled: "bg-red-500/20 text-red-300 border-red-500/40",
    inactive: "bg-slate-500/20 text-slate-300 border-slate-500/40",
  };
  return <Badge className={`border ${map[status] || map.inactive}`}>{status || "—"}</Badge>;
};
