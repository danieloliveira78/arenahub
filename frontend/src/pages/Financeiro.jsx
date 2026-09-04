import { useEffect, useState } from "react";
import { api, API } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Download, DollarSign, Clock, XCircle, TrendingUp, RotateCcw } from "lucide-react";
import { toast } from "sonner";

const brl = (v) => `R$ ${Number(v || 0).toFixed(2).replace(".", ",")}`;

export default function Financeiro() {
  const [data, setData] = useState(null);
  const [comps, setComps] = useState([]);
  const [compFilter, setCompFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    const params = {};
    if (compFilter !== "all") params.competition_id = compFilter;
    if (statusFilter !== "all") params.status = statusFilter;
    const [{data: f}, {data: c}] = await Promise.all([
      api.get("/admin/finance", { params }),
      api.get("/competitions"),
    ]);
    setData(f); setComps(c); setLoading(false);
  };

  useEffect(() => { load(); }, [compFilter, statusFilter]);

  const exportCsv = () => {
    const token = localStorage.getItem("session_token");
    const params = new URLSearchParams();
    if (compFilter !== "all") params.set("competition_id", compFilter);
    if (statusFilter !== "all") params.set("status", statusFilter);
    fetch(`${API}/admin/finance/export?${params.toString()}`, {
      credentials: "include",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(r => r.blob())
      .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = "financeiro.csv"; a.click();
        window.URL.revokeObjectURL(url);
      });
  };

  const refund = async (row) => {
    if (!confirm(`Reembolsar ${row.user_name || row.user_email} — R$ ${row.amount.toFixed(2)}?`)) return;
    try {
      await api.post(`/admin/refund/${row.session_id}`);
      toast.success("Reembolso realizado");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Erro no reembolso"); }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10" data-testid="financeiro-page">
      <div className="text-xs font-mono uppercase tracking-widest text-amber-400 mb-2">Painel do organizador</div>
      <h1 className="text-3xl sm:text-4xl font-extrabold mb-2">Financeiro</h1>
      <p className="text-slate-400 mb-8">Acompanhe o que entrou por torneio e exporte em CSV.</p>

      <div className="flex flex-wrap gap-3 mb-6">
        <Select value={compFilter} onValueChange={setCompFilter}>
          <SelectTrigger data-testid="filter-comp" className="w-64 bg-slate-900 border-slate-800"><SelectValue placeholder="Torneio"/></SelectTrigger>
          <SelectContent className="bg-slate-900 border-slate-800 text-slate-100">
            <SelectItem value="all">Todos os torneios</SelectItem>
            {comps.map(c => <SelectItem key={c.competition_id} value={c.competition_id}>{c.title}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger data-testid="filter-status" className="w-48 bg-slate-900 border-slate-800"><SelectValue placeholder="Status"/></SelectTrigger>
          <SelectContent className="bg-slate-900 border-slate-800 text-slate-100">
            <SelectItem value="all">Todos os status</SelectItem>
            <SelectItem value="paid">Pago</SelectItem>
            <SelectItem value="pending">Pendente</SelectItem>
            <SelectItem value="failed">Falhou</SelectItem>
          </SelectContent>
        </Select>
        <Button onClick={exportCsv} data-testid="export-csv-btn" className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold">
          <Download className="w-4 h-4 mr-1"/> Exportar CSV
        </Button>
      </div>

      {loading ? (
        <div className="text-slate-500">Carregando...</div>
      ) : (
        <>
          <div className="grid sm:grid-cols-3 gap-4 mb-8">
            <StatCard icon={DollarSign} label="Recebido" value={brl(data.totals.paid)} color="emerald" />
            <StatCard icon={Clock} label="Pendente" value={brl(data.totals.pending)} color="amber" />
            <StatCard icon={XCircle} label="Falhas / expirados" value={brl(data.totals.failed)} color="red" />
          </div>

          <section className="mb-10">
            <div className="flex items-center gap-2 mb-4">
              <TrendingUp className="w-5 h-5 text-emerald-400"/>
              <h2 className="text-xl font-bold">Por torneio</h2>
            </div>
            {data.per_competition.length === 0 ? (
              <div className="text-slate-500 text-sm border border-dashed border-slate-800 rounded-xl p-6">Sem pagamentos confirmados.</div>
            ) : (
              <div className="bg-slate-900/70 border border-slate-800 rounded-2xl overflow-hidden">
                {data.per_competition.map((r, i) => (
                  <div key={i} className="grid grid-cols-12 px-6 py-3 items-center border-b border-slate-800/60 last:border-0">
                    <div className="col-span-7 font-semibold">{r.title || "—"}</div>
                    <div className="col-span-2 text-center text-slate-400 text-sm">{r.count} inscrições</div>
                    <div className="col-span-3 text-right text-emerald-400 font-mono font-bold">{brl(r.total)}</div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section>
            <h2 className="text-xl font-bold mb-4">Todas as transações ({data.totals.count})</h2>
            <div className="bg-slate-900/70 border border-slate-800 rounded-2xl overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-900 text-xs uppercase tracking-widest text-slate-500 font-mono">
                  <tr>
                    <th className="text-left px-4 py-3">Data</th>
                    <th className="text-left px-4 py-3">Torneio</th>
                    <th className="text-left px-4 py-3">Atleta</th>
                    <th className="text-right px-4 py-3">Valor</th>
                    <th className="text-center px-4 py-3">Status</th>
                    <th className="text-right px-4 py-3">Ação</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r, i) => (
                    <tr key={i} className="border-t border-slate-800/60">
                      <td className="px-4 py-3 text-slate-400 whitespace-nowrap">{(r.created_at || "").slice(0, 10)}</td>
                      <td className="px-4 py-3">{r.competition_title || "—"}</td>
                      <td className="px-4 py-3">{r.user_name || r.user_email}</td>
                      <td className="px-4 py-3 text-right font-mono">{brl(r.amount)}</td>
                      <td className="px-4 py-3 text-center"><StatusPill status={r.payment_status}/></td>
                      <td className="px-4 py-3 text-right">
                        {r.payment_status === "paid" && (
                          <Button size="sm" variant="outline" onClick={()=>refund(r)}
                            data-testid={`refund-${r.session_id}`}
                            className="border-amber-700/40 text-amber-300 hover:bg-amber-950/30">
                            <RotateCcw className="w-3 h-3 mr-1"/> Reembolsar
                          </Button>
                        )}
                        {r.payment_status === "refunded" && (
                          <span className="text-xs text-slate-500">Reembolsado</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {data.rows.length === 0 && (
                    <tr><td colSpan="6" className="px-4 py-8 text-center text-slate-500">Nenhuma transação encontrada.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

const StatCard = ({ icon: Icon, label, value, color }) => (
  <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5">
    <div className="flex items-center gap-2 text-xs uppercase tracking-widest text-slate-500 font-mono mb-1">
      <Icon className={`w-4 h-4 text-${color}-400`}/> {label}
    </div>
    <div className={`text-2xl font-extrabold text-${color}-300`}>{value}</div>
  </div>
);

const StatusPill = ({ status }) => {
  const map = {
    paid:    "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
    pending: "bg-amber-500/20 text-amber-300 border-amber-500/30",
    failed:  "bg-red-500/20 text-red-300 border-red-500/30",
    expired: "bg-slate-500/20 text-slate-300 border-slate-500/30",
    refunded:"bg-purple-500/20 text-purple-300 border-purple-500/30",
  };
  return <Badge className={`border ${map[status] || map.pending}`}>{status}</Badge>;
};
