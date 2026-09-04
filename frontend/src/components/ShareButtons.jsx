import { Button } from "@/components/ui/button";
import { Share2, Link as LinkIcon, MessageCircle } from "lucide-react";
import { toast } from "sonner";

export const ShareButtons = ({ url, text, dataTestidPrefix = "share" }) => {
  const shareUrl = url || (typeof window !== "undefined" ? window.location.href : "");
  const message = `${text}\n\n${shareUrl}`;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl);
      toast.success("Link copiado!");
    } catch { toast.error("Não foi possível copiar"); }
  };

  const whatsapp = () => {
    const encoded = encodeURIComponent(message);
    window.open(`https://wa.me/?text=${encoded}`, "_blank", "noopener");
  };

  const native = async () => {
    if (navigator.share) {
      try { await navigator.share({ text, url: shareUrl }); }
      catch {}
    } else {
      copy();
    }
  };

  return (
    <div className="flex flex-wrap gap-2">
      <Button onClick={copy} data-testid={`${dataTestidPrefix}-copy`} variant="outline"
        size="sm" className="border-slate-700 hover:bg-slate-800">
        <LinkIcon className="w-3.5 h-3.5 mr-1"/> Copiar link
      </Button>
      <Button onClick={whatsapp} data-testid={`${dataTestidPrefix}-whatsapp`}
        size="sm" className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold">
        <MessageCircle className="w-3.5 h-3.5 mr-1"/> WhatsApp
      </Button>
      {typeof navigator !== "undefined" && navigator.share && (
        <Button onClick={native} data-testid={`${dataTestidPrefix}-native`}
          size="sm" variant="outline" className="border-slate-700 hover:bg-slate-800">
          <Share2 className="w-3.5 h-3.5 mr-1"/> Compartilhar
        </Button>
      )}
    </div>
  );
};

export default ShareButtons;
