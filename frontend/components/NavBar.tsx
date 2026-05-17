"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "📈 Auto Trading" },
  { href: "/scanner", label: "🔭 Market Scanner" },
  { href: "/admin", label: "⚙️ System Admin" },
];

export function NavBar() {
  const pathname = usePathname();

  return (
    <nav className="sticky top-0 z-50 w-full backdrop-blur-md bg-black/50 border-b border-zinc-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* 로고 영역 */}
          <Link href="/" className="flex-shrink-0 flex items-center gap-2 group">
            <div className="w-8 h-8 rounded bg-gradient-to-br from-blue-500 to-emerald-500 flex items-center justify-center font-bold text-white group-hover:scale-110 transition-transform">
              SA
            </div>
            <span className="font-bold text-xl tracking-tight">StockAuto</span>
          </Link>

          {/* 메뉴 영역 */}
          <div className="flex space-x-2">
            {navItems.map((item) => {
              const isActive =
                item.href === "/"
                  ? pathname === "/"
                  : pathname.startsWith(item.href);

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200",
                    isActive
                      ? "bg-zinc-800 text-white shadow-inner"
                      : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>
        </div>
      </div>
    </nav>
  );
}
