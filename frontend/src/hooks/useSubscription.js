import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

/**
 * Subscription/tenant status for the authenticated user.
 * Returns { info, loading, refresh, isBlocked }.
 *  - info: { tenant, effective_status, can_write, limits }
 *  - isBlocked: true when the tenant should be locked to view-only (edit-blocking).
 */
export function useSubscription() {
  const { user } = useAuth();
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!user) { setInfo(null); setLoading(false); return; }
    try {
      const { data } = await api.get("/me/tenant");
      setInfo(data);
    } catch {
      setInfo(null);
    } finally { setLoading(false); }
  }, [user]);

  useEffect(() => { load(); }, [load]);

  const status = info?.effective_status;
  const isBlocked = !!info && !info.can_write && user?.platform_role !== "super_admin";
  const isTrialing = status === "trialing";
  const isGrace = status === "grace_period";

  return { info, loading, refresh: load, isBlocked, isTrialing, isGrace, status };
}
