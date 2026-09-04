import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { XCircle } from "lucide-react";

export default function PaymentCancel() {
  return (
    <div className="min-h-[70vh] flex items-center justify-center px-4">
      <div className="max-w-md w-full bg-slate-900/80 border border-slate-800 rounded-2xl p-8 text-center" data-testid="payment-cancel">
        <XCircle className="w-14 h-14 mx-auto text-slate-500 mb-4" />
        <h1 className="text-2xl font-bold mb-2">Pagamento cancelado</h1>
        <p className="text-slate-400 mb-6">Você pode voltar e concluir sua inscrição a qualquer momento.</p>
        <Link to="/competicoes"><Button className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold">Voltar aos torneios</Button></Link>
      </div>
    </div>
  );
}
