"use client";
import { createContext, useContext, useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { getSupabase } from "@/lib/supabase";

type Role = "engineer" | "admin";
type AuthState = {
  session: Session | null;
  email: string | null;
  role: Role | null;
  loading: boolean;
  signOut: () => Promise<void>;
};

const Ctx = createContext<AuthState>({
  session: null, email: null, role: null, loading: true, signOut: async () => {},
});

export const useAuth = () => useContext(Ctx);

function roleOf(session: Session | null): Role | null {
  if (!session) return null;
  const m = session.user?.app_metadata as { role?: string } | undefined;
  return m?.role === "admin" ? "admin" : "engineer";
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const sb = getSupabase();
    if (!sb) { setLoading(false); return; }
    sb.auth.getSession().then(({ data }) => { setSession(data.session); setLoading(false); });
    const { data: sub } = sb.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  const signOut = async () => { await getSupabase()?.auth.signOut(); setSession(null); };

  return (
    <Ctx.Provider value={{
      session, email: session?.user?.email ?? null, role: roleOf(session), loading, signOut,
    }}>
      {children}
    </Ctx.Provider>
  );
}
