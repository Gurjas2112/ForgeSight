"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Activity, LogOut, ShieldCheck, User } from "lucide-react";
import { useAuth } from "./AuthProvider";

export function Navbar() {
  const { email, role, loading, signOut } = useAuth();
  const router = useRouter();

  return (
    <header className="flex items-center gap-3 px-5 h-14 border-b border-[#232B35] bg-[#0E1116] sticky top-0 z-30">
      <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
        <Activity size={18} className="text-[#FF6A2B]" />
        Forge<span className="text-[#4A90D9]">Sight</span>
      </Link>
      <span className="hidden sm:inline text-xs text-[#8B98A5] ml-1">Intelligent Maintenance Wizard · Tata Steel</span>

      <nav className="ml-auto flex items-center gap-3 text-sm">
        {email && <Link href="/dashboard" className="text-[#8B98A5] hover:text-[#E6EDF3]">Dashboard</Link>}
        {loading ? null : email ? (
          <>
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-[#161B22] border border-[#232B35] text-xs">
              {role === "admin" ? <ShieldCheck size={12} className="text-[#FF6A2B]" /> : <User size={12} className="text-[#4A90D9]" />}
              <span className="text-[#c3ced9]">{email}</span>
              <span className={role === "admin" ? "text-[#FF6A2B]" : "text-[#3FB68B]"}>· {role}</span>
            </span>
            <button type="button" onClick={async () => { await signOut(); router.push("/"); }}
              className="inline-flex items-center gap-1 text-[#8B98A5] hover:text-[#E5484D]">
              <LogOut size={14} /> Logout
            </button>
          </>
        ) : (
          <>
            <Link href="/login" className="px-3 py-1.5 rounded text-[#c3ced9] hover:text-[#E6EDF3]">Log in</Link>
            <Link href="/signup" className="px-3 py-1.5 rounded bg-[#4A90D9] text-white font-medium hover:bg-[#3a7bc0]">Sign up</Link>
          </>
        )}
      </nav>
    </header>
  );
}
