import { Dashboard } from "@/components/Dashboard";
import MarketHeader from "@/components/MarketHeader";

export default function Home() {
  return (
    <main className="min-h-screen bg-[#020617] text-slate-200">
      <MarketHeader />
      <Dashboard />
    </main>
  );
}
