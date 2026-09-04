import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Trophy, Award, Users, Calendar, ArrowLeft } from "lucide-react";
import { ShareButtons } from "@/components/ShareButtons";

export default function AthleteProfile() {
  const { name } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get(`/athletes/${encodeURIComponent(name)}`)
      .then(({data}) => setData(data))
      .finally(()=>setLoading(false));
  }, [name]);

  if (loading) return <div className="p-10 text-slate-400">Carregando...</div>;
  if (!data) return <div className="p-10 text-slate-400">Atleta não encontrado</div>;

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10" data-testid="athlete-profile">
      <Link to="/ranking" className="inline-flex items-center gap-1 text-sm text-slate-400 hover:text-emerald-400 mb-4">
        <ArrowLeft className="w-4 h-4"/> Voltar ao ranking
      </Link>

      <div className="bg-gradient-to-br from-emerald-500/10 via-slate-900 to-cyan-500/5 border border-slate-800 rounded-2xl p-8 mb-8">
        <div className="flex items-center gap-6 flex-wrap">
          <div className="w-24 h-24 rounded-full bg-emerald-500/20 border-2 border-emerald-500/40 flex items-center justify-center overflow-hidden text-3xl font-extrabold text-emerald-300">
            {data.picture ? <img src={data.picture} alt={data.player} className="w-full h-full object-cover"/> : data.player?.[0]}
          </div>
          <div className="flex-1 min-w-[200px]">
            <div className="text-xs font-mono uppercase tracking-widest text-emerald-400">Atleta</div>
            <h1 className="text-3xl sm:text-4xl font-extrabold mb-1">{data.player}</h1>
            {data.bio && <p className="text-slate-300 mt-2">{data.bio}</p>}
            <div className="mt-4">
              <ShareButtons
                text={`Confira o perfil de ${data.player} no ArenaHub — ${data.championships} campeonatos, ${data.wins} vitórias em ${data.tournaments} torneios.`}
                dataTestidPrefix="share-profile"
              />
            </div>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4 mt-6">
          <Stat icon={Trophy} label="Campeonatos" value={data.championships} color="amber"/>
          <Stat icon={Award} label="Vitórias" value={data.wins} color="emerald"/>
          <Stat icon={Calendar} label="Torneios" value={data.tournaments} color="cyan"/>
        </div>
      </div>

      <div className="grid md:grid-cols-3 gap-6">
        <div className="md:col-span-2">
          <h2 className="text-xl font-bold mb-4">Histórico</h2>
          {data.history.length === 0 ? (
            <div className="text-slate-500 text-sm border border-dashed border-slate-800 rounded-xl p-6 text-center">Sem torneios ainda.</div>
          ) : (
            <div className="space-y-3">
              {data.history.map((h, i) => (
                <Link to={`/competicoes/${h.competition?.competition_id}`} key={i}
                  className="block bg-slate-900/70 border border-slate-800 rounded-xl p-4 hover:border-emerald-500/40 transition-colors">
                  <div className="flex justify-between items-start">
                    <div>
                      <div className="text-xs text-emerald-400 font-mono uppercase">{h.competition?.type_name}</div>
                      <div className="font-bold">{h.competition?.title}</div>
                      {h.team && <div className="text-sm text-slate-400 mt-1">Dupla: {h.team.name}</div>}
                      <div className="text-xs text-slate-500 mt-1">{h.competition?.start_date}</div>
                    </div>
                    {h.champion && (
                      <div className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-amber-500/20 border border-amber-500/40 text-amber-300 text-xs font-bold">
                        <Trophy className="w-3 h-3"/> CAMPEÃO
                      </div>
                    )}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>

        <div>
          <h2 className="text-xl font-bold mb-4 flex items-center gap-2"><Users className="w-5 h-5 text-cyan-400"/> Parcerias</h2>
          {data.partners.length === 0 ? (
            <div className="text-slate-500 text-sm border border-dashed border-slate-800 rounded-xl p-4">Ainda sem parceiros registrados.</div>
          ) : (
            <div className="space-y-2">
              {data.partners.map(p => (
                <Link key={p.name} to={`/atletas/${encodeURIComponent(p.name)}`}
                  className="flex justify-between items-center bg-slate-900/70 border border-slate-800 rounded-xl p-3 hover:border-emerald-500/40">
                  <span className="font-medium">{p.name}</span>
                  <span className="text-xs text-slate-500">{p.count}x</span>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const Stat = ({ icon: Icon, label, value, color }) => (
  <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 text-center">
    <Icon className={`w-5 h-5 mx-auto mb-1 text-${color}-400`}/>
    <div className={`text-3xl font-extrabold text-${color}-300`}>{value}</div>
    <div className="text-xs text-slate-500 uppercase tracking-widest font-mono mt-1">{label}</div>
  </div>
);
