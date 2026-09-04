import { useEffect, useRef } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export default function AuthCallback() {
  const navigate = useNavigate();
  const location = useLocation();
  const { setUser } = useAuth();
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const fragment = location.hash.substring(1);
    const params = new URLSearchParams(fragment);
    const sessionId = params.get("session_id");

    if (!sessionId) {
      navigate("/", { replace: true });
      return;
    }

    (async () => {
      try {
        const { data } = await api.post("/auth/session", { session_id: sessionId });
        if (data.session_token) {
          localStorage.setItem("session_token", data.session_token);
        }
        setUser(data.user);
        // Clear the hash and go to dashboard
        window.history.replaceState({}, "", "/dashboard");
        navigate("/dashboard", { replace: true, state: { user: data.user } });
      } catch (e) {
        console.error("Auth callback error", e);
        navigate("/", { replace: true });
      }
    })();
  }, [location.hash, navigate, setUser]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0B0F17]" data-testid="auth-callback">
      <div className="text-center">
        <div className="w-12 h-12 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
        <p className="text-slate-400">Autenticando...</p>
      </div>
    </div>
  );
}
