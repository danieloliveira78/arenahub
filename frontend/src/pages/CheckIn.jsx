import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { QrCode, CheckCircle2, XCircle, Loader2, UserCheck, Camera, CameraOff } from "lucide-react";
import { toast } from "sonner";

export default function CheckIn() {
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [scannerOn, setScannerOn] = useState(false);
  const scannerRef = useRef(null);
  const html5Ref = useRef(null);

  const process = async (raw) => {
    const c = (raw || code).trim();
    if (!c) return;
    setLoading(true); setError(""); setResult(null);
    try {
      const { data } = await api.post(`/checkin/${c}`);
      setResult(data);
      if (data.already) toast.info("Atleta já havia feito check-in");
      else toast.success("Check-in confirmado!");
      setCode("");
    } catch (e) {
      setError(e.response?.data?.detail || "Erro ao processar");
      toast.error(e.response?.data?.detail || "Código inválido");
    } finally { setLoading(false); }
  };

  const onKey = (e) => { if (e.key === "Enter") process(); };

  useEffect(() => {
    if (!scannerOn) {
      if (html5Ref.current) {
        html5Ref.current.stop().then(() => html5Ref.current.clear()).catch(()=>{});
        html5Ref.current = null;
      }
      return;
    }
    (async () => {
      const { Html5Qrcode } = await import("html5-qrcode");
      const el = scannerRef.current;
      if (!el) return;
      const q = new Html5Qrcode("qr-scanner-region");
      html5Ref.current = q;
      try {
        await q.start(
          { facingMode: "environment" },
          { fps: 10, qrbox: { width: 260, height: 260 } },
          async (decoded) => {
            if (!loading) {
              setScannerOn(false);
              await process(decoded);
            }
          },
          () => {}
        );
      } catch (e) {
        toast.error("Não foi possível acessar a câmera");
        setScannerOn(false);
      }
    })();
    return () => {
      if (html5Ref.current) {
        html5Ref.current.stop().then(() => html5Ref.current?.clear()).catch(()=>{});
        html5Ref.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scannerOn]);

  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-10" data-testid="checkin-page">
      <div className="text-xs font-mono uppercase tracking-widest text-amber-400 mb-2">Painel do organizador</div>
      <h1 className="text-3xl sm:text-4xl font-extrabold mb-2">Check-in de atletas</h1>
      <p className="text-slate-400 mb-8">Escaneie o QR pelo celular ou digite o código manualmente.</p>

      <Tabs defaultValue="camera" className="mb-6">
        <TabsList className="bg-slate-900 border border-slate-800">
          <TabsTrigger value="camera" data-testid="tab-camera"><Camera className="w-4 h-4 mr-1"/> Câmera</TabsTrigger>
          <TabsTrigger value="code" data-testid="tab-code"><QrCode className="w-4 h-4 mr-1"/> Código</TabsTrigger>
        </TabsList>

        <TabsContent value="camera" className="mt-4">
          <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6">
            {!scannerOn ? (
              <div className="text-center py-6">
                <Camera className="w-12 h-12 mx-auto text-slate-500 mb-4"/>
                <p className="text-slate-400 mb-4">Aponte a câmera do celular para o QR code do atleta.</p>
                <Button onClick={()=>setScannerOn(true)} data-testid="start-camera-btn"
                  className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold">
                  <Camera className="w-4 h-4 mr-1"/> Iniciar câmera
                </Button>
              </div>
            ) : (
              <div>
                <div className="relative rounded-xl overflow-hidden bg-black">
                  <div id="qr-scanner-region" ref={scannerRef} className="w-full max-w-md mx-auto" />
                  <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                    <div className="w-64 h-64 border-2 border-emerald-400 rounded-2xl" />
                  </div>
                </div>
                <div className="mt-4 text-center">
                  <Button onClick={()=>setScannerOn(false)} data-testid="stop-camera-btn" variant="outline"
                    className="border-slate-700 hover:bg-slate-800">
                    <CameraOff className="w-4 h-4 mr-1"/> Parar câmera
                  </Button>
                </div>
              </div>
            )}
          </div>
        </TabsContent>

        <TabsContent value="code" className="mt-4">
          <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6">
            <Label htmlFor="ci-code" className="mb-2 block">Código de check-in</Label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <QrCode className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                <Input id="ci-code" data-testid="checkin-input" value={code} onChange={e=>setCode(e.target.value)}
                  onKeyDown={onKey} placeholder="chk_xxxxxxxxxxxxxxxx" autoFocus
                  className="pl-9 bg-slate-800 border-slate-700 text-slate-100 font-mono"/>
              </div>
              <Button onClick={()=>process()} disabled={loading} data-testid="checkin-btn"
                className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold">
                {loading ? <Loader2 className="w-4 h-4 animate-spin"/> : <><UserCheck className="w-4 h-4 mr-1"/> Confirmar</>}
              </Button>
            </div>
            <p className="text-xs text-slate-500 mt-2">Dica: leitor USB também funciona — digita o código e pressiona Enter.</p>
          </div>
        </TabsContent>
      </Tabs>

      {result && (
        <div data-testid="checkin-result" className={`rounded-2xl p-6 border ${
          result.already ? "border-amber-500/40 bg-amber-500/10" : "border-emerald-500/40 bg-emerald-500/10"
        }`}>
          <div className="flex items-start gap-3">
            {result.already ? <UserCheck className="w-8 h-8 text-amber-400 flex-shrink-0"/>
                            : <CheckCircle2 className="w-8 h-8 text-emerald-400 flex-shrink-0"/>}
            <div>
              <div className="text-lg font-bold">
                {result.already ? "Já havia feito check-in" : "Check-in confirmado"}
              </div>
              <div className="text-slate-300 mt-2">
                <div><strong>{result.registration.user_name}</strong></div>
                {result.registration.partner_name && <div>+ {result.registration.partner_name}</div>}
                <div className="text-sm text-slate-400 mt-1">{result.registration.user_email}</div>
                <div className="text-xs text-slate-500 mt-2">
                  Modalidade: {result.registration.mode === "individual" ? "Individual" : "Dupla"} · Pagamento: {result.registration.payment_status}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {error && !result && (
        <div className="rounded-2xl p-6 border border-red-500/40 bg-red-500/10 flex items-center gap-3">
          <XCircle className="w-6 h-6 text-red-400"/>
          <div>
            <div className="font-bold text-red-300">Não foi possível fazer o check-in</div>
            <div className="text-slate-300 text-sm">{error}</div>
          </div>
        </div>
      )}
    </div>
  );
}
