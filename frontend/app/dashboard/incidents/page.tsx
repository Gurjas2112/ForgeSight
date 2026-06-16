"use client";
import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { getIncidents } from "@/lib/api";
import type { Incident } from "@/lib/types";
import { StatusBadge } from "@/components/ui";
import { AuthGuard } from "@/components/AuthGuard";

function IncidentsList() {
  const searchParams = useSearchParams();
  const equipmentFilter = searchParams.get("equipment") || undefined;
  const [incidents, setIncidents] = useState<Incident[]>([]);
  useEffect(() => {
    getIncidents(equipmentFilter).then(setIncidents).catch(() => {});
  }, [equipmentFilter]);

  return (
    <>
      <h1 className="text-xl font-semibold mb-1">Incident replay</h1>
      <p className="text-sm text-[#8B98A5] mb-4">Production impact, failure progression, corrective action, and lessons learned.</p>
      <div className="space-y-2">
        {incidents.map((inc) => (
          <Link key={inc.id} href={`/dashboard/incidents/${inc.id}`} className="panel p-4 block hover:border-[#4A90D9]">
            <div className="flex items-start justify-between">
              <div>
                <div className="font-medium">{inc.fault_code || inc.id}</div>
                <div className="text-xs text-[#8B98A5]">{inc.equipment_name} · {inc.occurred_at}</div>
                <div className="text-sm text-[#9fb0c0] mt-1">{inc.symptoms || inc.root_cause}</div>
              </div>
              <div className="text-right">
                <div className="mono text-sm text-[#FF6A2B]">{inc.production_impact_label}</div>
                {inc.verified && <StatusBadge label="VERIFIED" sev="ok" />}
              </div>
            </div>
          </Link>
        ))}
        {incidents.length === 0 && <div className="panel p-4 text-sm text-[#8B98A5]">No incidents recorded.</div>}
      </div>
    </>
  );
}

export default function Page() {
  return (
    <AuthGuard>
      <Suspense fallback={<div className="text-sm text-[#8B98A5]">Loading…</div>}>
        <IncidentsList />
      </Suspense>
    </AuthGuard>
  );
}
