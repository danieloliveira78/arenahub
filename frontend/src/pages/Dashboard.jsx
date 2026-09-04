import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Trophy, Calendar, ExternalLink, Save, Camera, Loader2 } from "lucide-react";import { toast } from "sonner";
import { resizeImageToDataUrl } from "@/lib/resizeImage";

export default function Dashboard() {
  const { user, refresh } = useAuth();
  const [regs, setRegs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [bio, setBio] = useState("");
  const [savingBio, setSavingBio] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  useEffect(() => {
    api.get("/my-registrations").then(({data}) => setRegs(data)).finally(()=>setLoading(false));
    setBio(user?.bio || "");
  }, [user]);

  const saveBio = async () => {
    setSavingBio(true);
    try {
      await api.put("/me/profile", { bio });
      toast.success("Bio atualizada!");
      refresh();
    } catch (e) { toast.error("Erro ao salvar"); }
    finally { setSavingBio(false); }
  };

  const onPickPhoto = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 8 * 1024 * 1024) { toast.error("Imagem muito grande (máx 8MB)"); return; }
    setUploading(true);
    try {
      const dataUrl = await resizeImageToDataUrl(file, 320, 0.85);
      await api.put("/me/profile", { avatar: dataUrl });
      toast.success("Foto atualizada!");
      refresh();
    } catch (err) {
      toast.error("Erro ao enviar foto");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const avatarSrc = user?.avatar || user?.picture;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10" data-testid="dashboard">
      <h1 className="text-3xl sm:text-4xl font-extrabold mb-2">Olá, {user?.name?.split(" ")[0]}</h1>
      <p className="text-slate-400 mb-8">Seu perfil público e inscrições.</p>

      <div className="grid lg:grid-cols-3 gap-6 mb-10">
        <div className="lg:col-span-2 bg-slate-900/70 border border-slate-800 rounded-2xl p-6">
          <div className="flex items-start gap-6 flex-wrap">
            <div className="relative">
              <Avatar className="w-24 h-24 border-2 border-emerald-500/30">
                <AvatarImage src={avatarSrc} className="object-cover"/>
                <AvatarFallback className="bg-emerald-500/20 text-emerald-300 text-3xl font-bold">
                  {user?.name?.[0]}
                </AvatarFallback>
              </Avatar>
              <button onClick={()=>fileRef.current?.click()} data-testid="avatar-upload-btn"
                className="absolute -bottom-1 -right-1 w-9 h-9 rounded-full bg-emerald-500 hover:bg-emerald-400 flex items-center justify-center text-slate-950 shadow-lg">
                {uploading ? <Loader2 className="w-4 h-4 animate-spin"/> : <Camera className="w-4 h-4"/>}
              </button>
              <input type="file" accept="image/*" hidden ref={fileRef} onChange={onPickPhoto} data-testid="avatar-file-input"/>
            </div>
            <div className="flex-1 min-w-[240px]">
              <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                <Label htmlFor="bio" className="text-base font-bold">Sua bio pública</Label>
                <Link to={`/atletas/${encodeURIComponent(user?.name || "")}`}
                  className="text-xs text-emerald-400 hover:underline inline-flex items-center gap-1">
                  Ver perfil público <ExternalLink className="w-3 h-3"/>
                </Link>
              </div>
              <Textarea id="bio" data-testid="bio-input" value={bio} onChange={e=>setBio(e.target.value)}
                placeholder="Conte sua trajetória, estilo de jogo, títulos favoritos..."
                className="bg-slate-800 border-slate-700 text-slate-100 min-h-[80px]"/>
              <Button onClick={saveBio} disabled={savingBio} data-testid="save-bio-btn"
                className="mt-3 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold">
                <Save className="w-4 h-4 mr-1"/> Salvar bio
              </Button>
            </div>
          </div>
        </div>
        <div className="bg-gradient-to-br from-emerald-500/10 to-cyan-500/5 border border-emerald-500/30 rounded-2xl p-6">
          <div className="text-xs font-mono uppercase tracking-widest text-emerald-400 mb-2">Identidade Digital</div>
          <h3 className="font-bold mb-1">Compartilhe seu perfil</h3>
          <p className="text-slate-300 text-sm mb-4">Poste no story e mostre seu histórico de torneios.</p>
          <Link to={`/atletas/${encodeURIComponent(user?.name || "")}`}>
            <Button data-testid="view-profile-btn" className="w-full bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold">
              Abrir meu perfil público
            </Button>
          </Link>
        </div>
      </div>

      <h2 className="text-2xl font-bold mb-4">Minhas inscrições</h2>

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
              {r.mode === "dupla" && r.partner_name ? (
                <div className="mt-3 pt-3 border-t border-slate-800 flex items-center gap-3">
                  <Avatar className="w-10 h-10 border border-slate-700">
                    <AvatarImage src={r.partner_avatar} className="object-cover"/>
                    <AvatarFallback className="bg-cyan-500/20 text-cyan-300 text-sm font-bold">{r.partner_name?.[0]}</AvatarFallback>
                  </Avatar>
                  <div>
                    <div className="text-xs text-slate-500 uppercase tracking-widest font-mono">Sua dupla</div>
                    <div className="font-semibold text-slate-200">{r.partner_name}</div>
                  </div>
                </div>
              ) : (
                <div className="text-xs text-slate-500 mt-1">Modalidade: {r.mode === "individual" ? "Individual (aguardando sorteio)" : "Dupla"}</div>
              )}
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
