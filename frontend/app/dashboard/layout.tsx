import { DashboardTabs } from "@/components/DashboardTabs";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="max-w-7xl mx-auto px-5 py-6">
      <DashboardTabs />
      {children}
    </div>
  );
}
