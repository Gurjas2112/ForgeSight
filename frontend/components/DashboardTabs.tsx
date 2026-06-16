"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/dashboard", label: "Overview", exact: true },
  { href: "/dashboard/twin", label: "Twin" },
  { href: "/dashboard/evidence", label: "Evidence" },
  { href: "/dashboard/work-orders", label: "Work Orders" },
  { href: "/dashboard/incidents", label: "Incidents" },
  { href: "/dashboard/spares", label: "Spares" },
  { href: "/dashboard/reliability", label: "Reliability" },
  { href: "/dashboard/leadership", label: "Leadership" },
];

export function DashboardTabs() {
  const path = usePathname();
  return (
    <div className="border-b border-[#232B35] mb-5 -mx-5 px-5 overflow-x-auto">
      <nav className="flex gap-1 min-w-max">
        {TABS.map((t) => {
          const active = t.exact ? path === t.href : path.startsWith(t.href);
          return (
            <Link key={t.href} href={t.href}
              className={`px-3 py-2 text-sm whitespace-nowrap border-b-2 transition-colors ${
                active ? "border-[#4A90D9] text-[#E6EDF3]" : "border-transparent text-[#8B98A5] hover:text-[#c3ced9]"
              }`}>
              {t.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
