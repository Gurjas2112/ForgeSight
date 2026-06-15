"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getSupabase, authConfigured } from "@/lib/supabase";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("engineer@demo.forgesight");
  const [password, setPassword] = useState("forgesight-demo");
  const [err, setErr] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(undefined);
    const sb = getSupabase();
    if (!sb) { setErr("Auth is not configured (missing Supabase env)."); return; }
    setBusy(true);
    const { error } = await sb.auth.signInWithPassword({ email, password });
    setBusy(false);
    if (error) { setErr(error.message); return; }
    router.push("/dashboard");
  }

  return (
    <div className="max-w-sm mx-auto px-5 py-16">
      <h1 className="text-2xl font-semibold mb-1">Log in</h1>
      <p className="text-sm text-[#8B98A5] mb-6">Access the ForgeSight control room.</p>
      {!authConfigured() && <div className="panel p-3 mb-4 text-sm text-[#E8B931]">Supabase auth isn’t configured in this environment.</div>}
      <form onSubmit={submit} className="space-y-3">
        <Field label="Email" type="email" value={email} onChange={setEmail} />
        <Field label="Password" type="password" value={password} onChange={setPassword} />
        {err && <div className="text-sm text-[#E5484D]">{err}</div>}
        <button type="submit" disabled={busy} className="w-full py-2 rounded-lg bg-[#4A90D9] text-white font-medium disabled:opacity-50">
          {busy ? "Signing in…" : "Log in"}
        </button>
      </form>
      <p className="text-sm text-[#8B98A5] mt-4">No account? <Link href="/signup" className="text-[#4A90D9] hover:underline">Sign up</Link></p>
      <p className="text-xs text-[#8B98A5] mt-6">Demo: engineer@demo.forgesight / admin@demo.forgesight · <span className="mono">forgesight-demo</span></p>
    </div>
  );
}

function Field({ label, type, value, onChange }: { label: string; type: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="block">
      <span className="text-xs text-[#8B98A5]">{label}</span>
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)} required
        className="mt-1 w-full bg-[#0E1116] border border-[#232B35] rounded-lg px-3 py-2 text-sm outline-none focus:border-[#4A90D9]" />
    </label>
  );
}
