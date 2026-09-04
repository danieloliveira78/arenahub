import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Trash2, Pencil, Shield, Search } from "lucide-react";
import { toast } from "sonner";

export default function AdminUsers() {
  const [users, setUsers] = useState([]);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({});

  const load = async () => {
    const { data } = await api.get("/admin/users");
    setUsers(data);
  };
  useEffect(() => { load(); }, []);

  const openEdit = (u) => {
    setEditing(u);
    setForm({ name: u.name, email: u.email, is_admin: !!u.is_admin, bio: u.bio || "" });
  };

  const save = async () => {
    try {
      await api.put(`/admin/users/${editing.user_id}`, form);
      toast.success("Usuário atualizado");
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Erro"); }
  };

  const remove = async (u) => {
    if (!confirm(`Excluir ${u.name}? Todas as inscrições dele serão apagadas.`)) return;
    try {
      await api.delete(`/admin/users/${u.user_id}`);
      toast.success("Usuário excluído");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Erro"); }
  };

  const filtered = users.filter(u =>
    !query || u.name?.toLowerCase().includes(query.toLowerCase()) || u.email?.toLowerCase().includes(query.toLowerCase()));

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10" data-testid="admin-users-page">
      <div className="text-xs font-mono uppercase tracking-widest text-amber-400 mb-2">Painel do organizador</div>
      <h1 className="text-3xl sm:text-4xl font-extrabold mb-2">Usuários</h1>
      <p className="text-slate-400 mb-6">Edite nome, e-mail, permissão de admin e bio de qualquer atleta.</p>

      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500"/>
        <Input data-testid="users-search" placeholder="Buscar nome ou e-mail..." value={query} onChange={e=>setQuery(e.target.value)}
          className="pl-9 bg-slate-900 border-slate-800 text-slate-100"/>
      </div>

      <div className="bg-slate-900/70 border border-slate-800 rounded-2xl overflow-hidden">
        {filtered.map(u => (
          <div key={u.user_id} data-testid={`user-row-${u.user_id}`}
            className="grid grid-cols-12 gap-2 items-center px-6 py-4 border-b border-slate-800/60 last:border-0">
            <div className="col-span-6 flex items-center gap-3">
              <Avatar className="w-10 h-10 border border-slate-700">
                <AvatarImage src={u.picture} className="object-cover"/>
                <AvatarFallback className="bg-emerald-500/20 text-emerald-300 font-bold">{u.name?.[0]}</AvatarFallback>
              </Avatar>
              <div>
                <div className="font-semibold">{u.name}</div>
                <div className="text-xs text-slate-500">{u.email}</div>
              </div>
            </div>
            <div className="col-span-2 text-center text-sm text-slate-400">{u.registrations_count} insc.</div>
            <div className="col-span-2 text-center">
              {u.is_admin && <Badge className="bg-amber-500/20 text-amber-300 border border-amber-500/40"><Shield className="w-3 h-3 mr-1"/>Admin</Badge>}
            </div>
            <div className="col-span-2 flex justify-end gap-2">
              <Button size="sm" variant="outline" onClick={()=>openEdit(u)} data-testid={`edit-user-${u.user_id}`}
                className="border-slate-700 hover:bg-slate-800"><Pencil className="w-3 h-3"/></Button>
              <Button size="sm" variant="outline" onClick={()=>remove(u)} data-testid={`del-user-${u.user_id}`}
                className="border-red-800/40 text-red-300 hover:bg-red-950/40"><Trash2 className="w-3 h-3"/></Button>
            </div>
          </div>
        ))}
        {filtered.length === 0 && <div className="p-8 text-center text-slate-500">Nenhum usuário encontrado.</div>}
      </div>

      <Dialog open={!!editing} onOpenChange={(o)=>!o && setEditing(null)}>
        <DialogContent className="bg-slate-900 border-slate-800 text-slate-100">
          <DialogHeader><DialogTitle>Editar usuário</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div><Label>Nome</Label>
              <Input value={form.name || ""} onChange={e=>setForm(f=>({...f, name:e.target.value}))} data-testid="user-edit-name" className="bg-slate-800 border-slate-700"/></div>
            <div><Label>E-mail</Label>
              <Input value={form.email || ""} onChange={e=>setForm(f=>({...f, email:e.target.value}))} data-testid="user-edit-email" className="bg-slate-800 border-slate-700"/></div>
            <div><Label>Bio</Label>
              <Input value={form.bio || ""} onChange={e=>setForm(f=>({...f, bio:e.target.value}))} data-testid="user-edit-bio" className="bg-slate-800 border-slate-700"/></div>
            <div className="flex items-center gap-3">
              <Switch checked={!!form.is_admin} onCheckedChange={v=>setForm(f=>({...f, is_admin:v}))} data-testid="user-edit-admin"/>
              <Label>Administrador</Label>
            </div>
          </div>
          <DialogFooter>
            <Button onClick={save} data-testid="user-save-btn" className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold">Salvar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
