"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getSupabase, authConfigured } from "@/lib/supabase";
import { postSignup } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(undefined);
    const sb = getSupabase();
    if (!sb) { setErr("Auth is not configured (missing Supabase env)."); return; }
    setBusy(true);
    try {
      // create a pre-confirmed engineer via the backend admin API, then sign in.
      // Admin accounts are provisioned by an administrator — public signup is engineer-only.
      await postSignup({ email, password, full_name: fullName });
      const { error } = await sb.auth.signInWithPassword({ email, password });
      if (error) throw new Error(error.message);
      router.push("/dashboard");
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-sm mx-auto px-5 py-16">
      <h1 className="text-2xl font-semibold mb-1">Create account</h1>
      <p className="text-sm text-[#8B98A5] mb-6">Sign up as a maintenance engineer.</p>
      {!authConfigured() && <div className="panel p-3 mb-4 text-sm text-[#E8B931]">Supabase auth isn’t configured in this environment.</div>}
      <form onSubmit={submit} className="space-y-3">
        <Field label="Full name" type="text" value={fullName} onChange={setFullName} required={false} />
        <Field label="Email" type="email" value={email} onChange={setEmail} />
        <Field label="Password (min 6 chars)" type="password" value={password} onChange={setPassword} />
        <p className="text-xs text-[#8B98A5]">New accounts are created with the <span className="text-[#9fb0c0]">engineer</span> role. Admin accounts are provisioned by an administrator.</p>
        {err && <div className="text-sm text-[#E5484D]">{err}</div>}
        <button type="submit" disabled={busy} className="w-full py-2 rounded-lg bg-[#4A90D9] text-white font-medium disabled:opacity-50">
          {busy ? "Creating…" : "Sign up"}
        </button>
      </form>
      <p className="text-sm text-[#8B98A5] mt-4">Already have an account? <Link href="/login" className="text-[#4A90D9] hover:underline">Log in</Link></p>
    </div>
  );
}

function Field({ label, type, value, onChange, required = true }: { label: string; type: string; value: string; onChange: (v: string) => void; required?: boolean }) {
  return (
    <label className="block">
      <span className="text-xs text-[#8B98A5]">{label}</span>
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)} required={required}
        className="mt-1 w-full bg-[#0E1116] border border-[#232B35] rounded-lg px-3 py-2 text-sm outline-none focus:border-[#4A90D9]" />
    </label>
  );
}
