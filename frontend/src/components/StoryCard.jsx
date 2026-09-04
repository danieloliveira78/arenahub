import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Download, Sparkles, Loader2 } from "lucide-react";
import { toast } from "sonner";

/**
 * Renders a 1080x1920 story card (visually offscreen) and downloads it as PNG via html2canvas.
 * Props: title, subtitle, playerName, playerAvatar (url|dataURL), competitionTitle, hashtag
 */
export default function StoryCard({
  title = "CAMPEÃO",
  subtitle = "ArenaHub",
  playerName,
  playerAvatar,
  competitionTitle,
  hashtag,
  triggerLabel = "Baixar Story",
  testId = "download-story-btn",
}) {
  const ref = useRef(null);
  const [busy, setBusy] = useState(false);

  const download = async () => {
    if (!ref.current) return;
    setBusy(true);
    try {
      const { default: html2canvas } = await import("html2canvas");
      const canvas = await html2canvas(ref.current, {
        backgroundColor: "#0B0F17",
        scale: 1, useCORS: true, allowTaint: true,
        width: 1080, height: 1920,
      });
      const link = document.createElement("a");
      link.download = `story-${(playerName || "campeao").replace(/\s+/g, "-").toLowerCase()}.png`;
      link.href = canvas.toDataURL("image/png");
      link.click();
      toast.success("Story baixado!");
    } catch (e) {
      toast.error("Erro ao gerar story");
    } finally { setBusy(false); }
  };

  return (
    <>
      <Button onClick={download} disabled={busy} data-testid={testId}
        className="bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold">
        {busy ? <Loader2 className="w-4 h-4 animate-spin"/> : <><Download className="w-4 h-4 mr-1"/> {triggerLabel}</>}
      </Button>

      {/* Off-screen renderable story card */}
      <div style={{
        position: "fixed", left: "-9999px", top: 0, width: 1080, height: 1920,
        pointerEvents: "none",
      }}>
        <div ref={ref} style={{
          width: 1080, height: 1920, position: "relative", overflow: "hidden",
          background: "linear-gradient(160deg, #0B0F17 0%, #0f1a24 60%, #0B1a12 100%)",
          fontFamily: "Outfit, Plus Jakarta Sans, sans-serif", color: "#F8FAFC",
        }}>
          {/* Glow orbs */}
          <div style={{
            position: "absolute", top: -200, left: -200, width: 700, height: 700,
            background: "radial-gradient(circle, rgba(34,197,94,0.35), transparent 70%)",
          }}/>
          <div style={{
            position: "absolute", bottom: -260, right: -260, width: 800, height: 800,
            background: "radial-gradient(circle, rgba(6,182,212,0.28), transparent 70%)",
          }}/>

          {/* Header */}
          <div style={{ position: "relative", padding: "80px 80px 0" }}>
            <div style={{
              display: "inline-flex", alignItems: "center", gap: 12,
              padding: "10px 22px", borderRadius: 999,
              background: "rgba(34,197,94,0.15)", border: "2px solid rgba(34,197,94,0.5)",
              color: "#22C55E", fontSize: 26, fontWeight: 700, letterSpacing: 4,
              textTransform: "uppercase",
            }}>
              <Sparkles style={{ width: 22, height: 22 }}/> {subtitle}
            </div>
          </div>

          {/* Trophy */}
          <div style={{ position: "relative", textAlign: "center", marginTop: 100 }}>
            <div style={{ fontSize: 280, lineHeight: 1 }}>🏆</div>
            <div style={{
              fontSize: 120, fontWeight: 900, letterSpacing: -4,
              color: "#F59E0B", textShadow: "0 0 60px rgba(245,158,11,0.5)",
              marginTop: 20,
            }}>{title}</div>
          </div>

          {/* Player Avatar + name */}
          <div style={{ position: "relative", textAlign: "center", marginTop: 80 }}>
            {playerAvatar ? (
              <img src={playerAvatar} crossOrigin="anonymous" alt=""
                style={{
                  width: 320, height: 320, borderRadius: "50%", objectFit: "cover",
                  border: "8px solid #22C55E",
                  boxShadow: "0 0 80px rgba(34,197,94,0.5)",
                }}/>
            ) : (
              <div style={{
                width: 320, height: 320, borderRadius: "50%",
                background: "rgba(34,197,94,0.2)", border: "8px solid #22C55E",
                display: "inline-flex", alignItems: "center", justifyContent: "center",
                fontSize: 160, fontWeight: 900, color: "#22C55E",
              }}>{(playerName || "?")[0]}</div>
            )}
            <div style={{ fontSize: 84, fontWeight: 900, marginTop: 40, letterSpacing: -2 }}>
              {playerName}
            </div>
            {competitionTitle && (
              <div style={{ fontSize: 40, color: "#94A3B8", marginTop: 20, padding: "0 80px" }}>
                {competitionTitle}
              </div>
            )}
          </div>

          {/* Footer */}
          <div style={{
            position: "absolute", left: 0, right: 0, bottom: 80,
            textAlign: "center",
          }}>
            {hashtag && (
              <div style={{ fontSize: 44, color: "#22C55E", fontWeight: 800, letterSpacing: 2 }}>
                #{hashtag}
              </div>
            )}
            <div style={{ fontSize: 30, color: "#64748B", marginTop: 16, letterSpacing: 4 }}>
              ARENAHUB · TORNEIOS
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
