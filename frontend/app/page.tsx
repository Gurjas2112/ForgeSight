import Link from "next/link";
import {
  ArrowRight, ShieldCheck, Brain, FileSearch, Gauge, Activity, Lock, Workflow,
} from "lucide-react";

const FLOW = [
  { n: 1, t: "Fault or alert comes in", d: "A trip code, an anomaly alert, or a natural-language question from the floor." },
  { n: 2, t: "Governed agents investigate", d: "Diagnostic · Reliability · Supervisor · Planner · Analyst — each under an explicit charter, scoped tools, budgets." },
  { n: 3, t: "Evidence-cited answer", d: "A structured card: ranked root causes, RUL, priority, spares — every claim cited to a manual, record, or trend." },
  { n: 4, t: "Human commits, audited", d: "Agents propose; the engineer approves commitments; every allow/deny is timestamped in the audit log." },
];

const FEATURES = [
  { icon: Brain, t: "On-prem SLM (Qwen2.5-3B)", d: "Fine-tuned via QLoRA and served locally through Ollama under constrained decoding; the public demo falls back to a hosted LLM (Groq) since cloud has no GPU." },
  { icon: FileSearch, t: "Cited, or it refuses", d: "A code-level guardrail makes a fabricated citation physically impossible." },
  { icon: Gauge, t: "Real ML inference", d: "Anomaly runs live on sensors; defect/failure/Azure/RUL run live on held-out benchmark rows — every number reproducible, shown in the model panel." },
  { icon: Workflow, t: "Deterministic scoring", d: "Priority & procurement from auditable rules, never an LLM guess." },
  { icon: ShieldCheck, t: "Human-in-the-loop", d: "COMMIT actions pause for explicit engineer approval." },
  { icon: Lock, t: "Role-based access", d: "Engineer and Admin roles, JWT-verified on every request." },
];

const MODELS = [
  ["Anomaly (live on sensors)", "recall 1.0 · 8.7 d lead"],
  ["RUL — C-MAPSS benchmark", "RMSE 16.4 cycles · serve = trend extrapolation"],
  ["Failure (AI4I)", "recall 0.91 · PR-AUC 0.80"],
  ["Defect (Steel Plates)", "PR-AUC 0.80 · live LightGBM"],
  ["Azure PdM 24h-ahead", "PR-AUC 0.90 · recall 0.92"],
];

export default function Landing() {
  return (
    <div className="max-w-6xl mx-auto px-5">
      {/* Hero */}
      <section className="pt-16 pb-12 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#161B22] border border-[#232B35] text-xs text-[#8B98A5] mb-5">
          <Activity size={13} className="text-[#FF6A2B]" /> Tata Steel AI Hackathon 2026
        </div>
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight">
          From fault code to fix plan in <span className="text-[#FF6A2B]">90 seconds</span>
        </h1>
        <p className="mt-4 text-lg text-[#9fb0c0] max-w-2xl mx-auto">
          ForgeSight is a governed multi-agent maintenance wizard for steel plants — every answer
          cited, every score deterministic, every agent under an explicit charter, running fully
          on-premise on an open-source SLM.
        </p>
        <div className="mt-7 flex items-center justify-center gap-3">
          <Link href="/signup" className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-[#4A90D9] text-white font-medium hover:bg-[#3a7bc0]">
            Get started <ArrowRight size={16} />
          </Link>
          <Link href="/login" className="px-5 py-2.5 rounded-lg border border-[#232B35] text-[#c3ced9] hover:border-[#4A90D9]">
            Log in
          </Link>
        </div>
        <p className="mt-3 text-xs text-[#8B98A5]">
          Demo logins — engineer@demo.forgesight / admin@demo.forgesight · password <span className="mono">forgesight-demo</span>
        </p>
      </section>

      {/* Flow */}
      <section className="py-10">
        <h2 className="text-center text-sm uppercase tracking-wider text-[#8B98A5] mb-6">How it works</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          {FLOW.map((s) => (
            <div key={s.n} className="panel p-4">
              <div className="mono text-[#4A90D9] text-sm">0{s.n}</div>
              <div className="font-medium mt-1">{s.t}</div>
              <div className="text-sm text-[#8B98A5] mt-1">{s.d}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section className="py-10">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {FEATURES.map((f) => (
            <div key={f.t} className="panel p-4">
              <f.icon size={18} className="text-[#4A90D9]" />
              <div className="font-medium mt-2">{f.t}</div>
              <div className="text-sm text-[#8B98A5] mt-1">{f.d}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Models */}
      <section className="py-10">
        <div className="panel p-5">
          <div className="text-sm font-medium mb-3">About the models — benchmarks validate the method, the simulation validates the system (live inferences on the dashboard)</div>
          <div className="flex flex-wrap gap-2">
            {MODELS.map(([m, s]) => (
              <span key={m} className="text-xs px-2.5 py-1 rounded bg-[#1C232C] border border-[#232B35]">
                <span className="text-[#c3ced9]">{m}</span> <span className="text-[#8B98A5]">· {s}</span>
              </span>
            ))}
          </div>
        </div>
      </section>

      <section className="py-12 text-center">
        <h2 className="text-2xl font-semibold">Ready to see it on a live plant?</h2>
        <p className="text-[#8B98A5] mt-2">Sign in and open the control room.</p>
        <Link href="/dashboard" className="mt-5 inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-[#FF6A2B] text-black font-medium hover:opacity-90">
          Open the dashboard <ArrowRight size={16} />
        </Link>
      </section>

      <footer className="py-8 text-center text-xs text-[#8B98A5] border-t border-[#232B35]">
        ForgeSight · governed multi-agent maintenance decision-support · on-prem capable
      </footer>
    </div>
  );
}
