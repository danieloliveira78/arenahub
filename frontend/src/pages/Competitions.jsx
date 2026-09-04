import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Calendar, MapPin, Trophy, Users, Search } from "lucide-react";

export default function Competitions() {
  const [comps, setComps] = useState([]);
  const [types, setTypes] = useState([]);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        // Bootstrap default types if empty
        await api.post("/seed-defaults").catch(() => {});
        const [{ data: cs }, { data: ts }] = await Promise.all([
          api.get("/competitions"),
          api.get("/competition-types"),
        ]);
        setComps(cs); setTypes(ts);
      } finally { setLoading(false); }
    })();
  }, []);

  const filtered = comps
    .filter(c => filter === "all" || c.type_id === filter)
    .filter(c => c.title.toLowerCase().includes(query.toLowerCase()));

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      <div className="mb-8">
        <h1 className="text-3xl sm:text-4xl font-extrabold mb-2" data-testid="competitions-title">Torneios abertos</h1>
        <p className="text-slate-400">Escolha uma competição e faça sua inscrição.</p>
      </div>

      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <Input data-testid="competitions-search" placeholder="Buscar torneio..." value={query} onChange={(e)=>setQuery(e.target.value)}
            className="pl-9 bg-slate-900 border-slate-800 text-slate-100 placeholder:text-slate-500 focus-visible:ring-emerald-500" />
        </div>
      </div>

      <div className="flex flex-wrap gap-2 mb-8">
        <button onClick={()=>setFilter("all")} data-testid="filter-all"
          className={`px-4 py-1.5 rounded-full text-sm font-medium border transition-colors ${
            filter==="all" ? "bg-emerald-500 text-slate-950 border-emerald-500" : "border-slate-700 text-slate-300 hover:border-slate-500"
          }`}>Todos</button>
        {types.map(t => (
          <button key={t.type_id} onClick={()=>setFilter(t.type_id)} data-testid={`filter-${t.name}`}
            className={`px-4 py-1.5 rounded-full text-sm font-medium border transition-colors ${
              filter===t.type_id ? "bg-emerald-500 text-slate-950 border-emerald-500" : "border-slate-700 text-slate-300 hover:border-slate-500"
            }`}>{t.name}</button>
        ))}
      </div>

      {loading ? (
        <div className="text-slate-500">Carregando...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-20 border border-dashed border-slate-800 rounded-2xl">
          <Trophy className="w-10 h-10 mx-auto text-slate-600 mb-3" />
          <p className="text-slate-400">Nenhum torneio encontrado. Peça ao administrador para criar um.</p>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filtered.map((c) => (
            <Link to={`/competicoes/${c.competition_id}`} key={c.competition_id} data-testid={`comp-card-${c.competition_id}`}
              className="group bg-slate-900/70 border border-slate-800 rounded-2xl overflow-hidden hover:border-emerald-500/40 hover:shadow-lg hover:shadow-emerald-500/10 transition-all">
              <div className="h-32 relative bg-gradient-to-br from-emerald-500/20 via-slate-900 to-cyan-500/10 flex items-center justify-center">
                <Trophy className="w-12 h-12 text-emerald-400/70" />
                <Badge className={`absolute top-3 right-3 ${c.fee > 0 ? "bg-amber-500/20 text-amber-300 border-amber-500/30" : "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"} border`}>
                  {c.fee > 0 ? `R$ ${c.fee.toFixed(2)}` : "GRATUITO"}
                </Badge>
              </div>
              <div className="p-5">
                <div className="text-xs font-mono uppercase text-emerald-400 mb-1 tracking-widest">{c.type_name}</div>
                <h3 className="text-lg font-bold mb-3 group-hover:text-emerald-400 transition-colors">{c.title}</h3>
                <div className="space-y-1.5 text-sm text-slate-400">
                  <div className="flex items-center gap-2"><Calendar className="w-3.5 h-3.5"/> {c.start_date} → {c.end_date}</div>
                  {c.location && <div className="flex items-center gap-2"><MapPin className="w-3.5 h-3.5"/> {c.location}</div>}
                  <div className="flex items-center gap-2"><Trophy className="w-3.5 h-3.5 text-amber-400"/> {c.prize}</div>
                  <div className="flex items-center gap-2"><Users className="w-3.5 h-3.5 text-cyan-400"/> {c.registered_count}/{c.max_slots} inscritos</div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
