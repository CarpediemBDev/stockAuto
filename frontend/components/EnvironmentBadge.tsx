"use client";

export function EnvironmentBadge() {
  // NEXT_PUBLIC_* 변수는 빌드 타임에 주입되므로 서버/클라이언트 간 값이 동일하여 Hydration Mismatch가 발생하지 않습니다.
  const env = process.env.NEXT_PUBLIC_APP_ENV || "unknown";

  if (env === "unknown" || !env) return null;

  let bgColor = "bg-zinc-800 text-zinc-300 border-zinc-600"; // 기본 (unknown)
  let label = "UNKNOWN ENV";

  if (env === "local") {
    bgColor = "bg-blue-600/90 text-white shadow-blue-500/50 border-blue-400";
    label = "LOCAL";
  } else if (env === "dev") {
    bgColor = "bg-amber-500/90 text-white shadow-amber-500/50 border-amber-400";
    label = "DEV";
  } else if (env === "prod") {
    bgColor = "bg-red-600/90 text-white shadow-red-500/50 border-red-500 animate-pulse";
    label = "PROD";
  }

  return (
    <div className={`fixed bottom-24 left-0 z-50 pl-3 pr-5 py-2 rounded-r-full shadow-lg backdrop-blur-md border border-l-0 pointer-events-none flex items-center gap-2 transition-all duration-500 hover:pr-8 ${bgColor}`}>
      <div className="w-1.5 h-1.5 rounded-full bg-white animate-pulse"></div>
      <span className="text-[11px] font-black tracking-widest uppercase">{label}</span>
    </div>
  );
}
