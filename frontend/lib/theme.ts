/**
 * 주식 및 금융 도메인 수익/손실 색상 SSOT
 * 글로벌 핀테크 표준(수익=Emerald/초록, 손실=Rose/빨강)을 기본값으로 단일화합니다.
 */
export function getProfitColor(
  value: number | null | undefined,
  options?: {
    bg?: boolean;
    border?: boolean;
    badge?: boolean;
    neutralZero?: boolean;
    /** 게이지·막대처럼 불투명 채움이 필요한 경우 (텍스트 색은 반환하지 않는다) */
    solid?: boolean;
  }
): string {
  if (value === null || value === undefined) return "text-zinc-400";

  if (options?.neutralZero && value === 0) {
    if (options?.badge) return "bg-zinc-800 text-zinc-400 border border-zinc-700/50";
    if (options?.bg) return "bg-zinc-800 text-zinc-400";
    if (options?.solid) return "bg-zinc-700";
    return "text-zinc-400";
  }

  const isProfit = value >= 0;

  if (options?.solid) {
    return isProfit ? "bg-emerald-500" : "bg-rose-500";
  }

  if (options?.badge) {
    return isProfit
      ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
      : "bg-rose-500/10 text-rose-400 border border-rose-500/20";
  }

  if (options?.bg && options?.border) {
    return isProfit
      ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
      : "bg-rose-500/15 text-rose-400 border border-rose-500/30";
  }

  if (options?.bg) {
    return isProfit ? "bg-emerald-500/20 text-emerald-400" : "bg-rose-500/20 text-rose-400";
  }

  return isProfit ? "text-emerald-400" : "text-rose-400";
}

/**
 * AI 시장 체제(Regime) 뱃지 및 색상 SSOT
 */
export function getRegimeTheme(regime: string | null | undefined): {
  textColor: string;
  badgeClass: string;
  dotColor: string;
  label: string;
} {
  const norm = (regime || "").toUpperCase();
  if (norm === "BULLISH" || norm === "BULL") {
    return {
      textColor: "text-emerald-400",
      badgeClass: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
      dotColor: "bg-emerald-500",
      label: "BULLISH",
    };
  }
  if (norm === "BEARISH" || norm === "BEAR") {
    return {
      textColor: "text-rose-400",
      badgeClass: "bg-rose-500/10 text-rose-400 border border-rose-500/20",
      dotColor: "bg-rose-500",
      label: "BEARISH",
    };
  }
  if (norm === "SIDEWAYS" || norm === "VOLATILE" || norm === "NEUTRAL") {
    return {
      textColor: "text-amber-400",
      badgeClass: "bg-amber-500/10 text-amber-400 border border-amber-500/20",
      dotColor: "bg-amber-500",
      label: norm || "NEUTRAL",
    };
  }
  return {
    textColor: "text-zinc-400",
    badgeClass: "bg-zinc-800 text-zinc-400 border border-zinc-700/50",
    dotColor: "bg-zinc-500",
    label: norm || "UNKNOWN",
  };
}

/**
 * 공통 글래스모피즘 표면(Surface) 스타일 SSOT.
 * components/ui의 프리미티브(Card, Modal, Input)가 이 문자열을 가져다 쓴다.
 * 프리미티브를 쓰지 않는 화면도 여기서 같은 값을 참조해야 하며, 클래스 문자열을 다시 적지 않는다.
 * 폭·여백처럼 호출부마다 달라지는 값은 여기 넣지 않고 호출부에서 합성한다.
 */
export const surfaceStyles = {
  card: "bg-surface-card/80 backdrop-blur-xl border border-zinc-800/80 rounded-2xl shadow-xl",
  cardSubtle: "bg-surface-card-subtle/70 backdrop-blur-md border border-zinc-800/60 rounded-xl",
  cardHighlight: "bg-surface-card-highlight/90 backdrop-blur-xl border border-indigo-500/30 rounded-2xl shadow-2xl",
  modalOverlay: "fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 animate-in fade-in duration-200",
  modalContent: "bg-surface-card border border-zinc-800 rounded-3xl w-full p-6 relative shadow-2xl animate-in zoom-in-95 duration-200 overflow-hidden max-h-[90vh] flex flex-col",
  input: "w-full bg-surface-card-subtle border border-zinc-800 rounded-xl py-2.5 text-sm text-slate-200 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500/80 transition-all duration-200",
} as const;

/**
 * 차트용 손익 색상.
 * Recharts의 stroke·stopColor는 SVG 프레젠테이션 속성이라 var()를 해석하지 못하므로,
 * globals.css의 --profit/--loss와 같은 값을 JS 상수로 둔다. 두 곳을 함께 바꿔야 한다.
 */
export const chartColors = {
  profit: "#10b981",
  loss: "#f43f5e",
} as const;
