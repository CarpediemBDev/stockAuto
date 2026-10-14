/**
 * 외부 보유분 수확 모드의 가격 기준선. 위임 설정 모달과 종목 정보 모달이 같은 값을 보여야 하므로
 * 계산은 여기 한 곳에만 둔다.
 *
 * 퍼센트(harvest_arm_pct·harvest_trailing_pct)는 스케줄러가 관측해 저장한 값이다. 무장 폭은 ATR 파생이고
 * 트레일링 폭은 2026-09-26부터 5% 고정이지만, 화면은 둘 다 저장된 값을 그대로 읽는다.
 * 아직 관측되지 않았으면 null이고, 그때는 추정하지 않고 null을 돌려준다 - 추정치를 보여주면
 * 실제 판정과 어긋난 숫자를 사용자가 기준으로 삼게 된다.
 *
 * 매도 하한(harvest_floor_price)은 서버가 스케줄러와 같은 함수로 계산해 내려준다. 수수료 포함
 * 본전가와 관측 시작가 중 높은 값이며, 여기서 다시 계산하지 않는다.
 */
export interface HarvestLevelInput {
  current_price?: number;
  highest_price: number;
  harvest_armed?: boolean;
  observed_base_price?: number | null;
  harvest_arm_pct?: number | null;
  harvest_trailing_pct?: number | null;
  harvest_floor_price?: number | null;
}

export interface HarvestLevels {
  /** 무장 전: 이 가격에 닿으면 고점 추적을 시작한다. 무장 뒤에는 의미가 없어 null. */
  armPrice: number | null;
  /** 무장 뒤: 고점 대비 트레일링 폭만큼 내려온 매도 기준선. 무장 전에는 null. */
  stopPrice: number | null;
  /** 수확 매도 하한. 이 가격 이하에서는 기준선을 이탈해도 팔지 않는다. 평단을 모르면 null. */
  floorPrice: number | null;
  /** 매도 기준선이 하한 이하라 지금은 수확 매도가 일어날 수 없는 상태. */
  noSellZone: boolean;
}

export function harvestLevels(h: HarvestLevelInput): HarvestLevels {
  // 관측 시작가가 아직 없으면 현재가로 대신한다(기존 위임 모달의 표시 규칙과 동일).
  const base = h.observed_base_price ?? h.current_price ?? null;
  const armPrice =
    !h.harvest_armed && h.harvest_arm_pct != null && base != null
      ? base * (1 + h.harvest_arm_pct / 100)
      : null;
  const stopPrice =
    h.harvest_armed && h.harvest_trailing_pct != null && h.highest_price > 0
      ? h.highest_price * (1 - h.harvest_trailing_pct / 100)
      : null;
  const floorPrice = h.harvest_floor_price ?? null;
  // 서버 판정은 current > floor 이고 current <= stop 이어야 판다. stop <= floor면 그 구간이 비어 있다.
  const noSellZone = stopPrice != null && floorPrice != null && stopPrice <= floorPrice;
  return { armPrice, stopPrice, floorPrice, noSellZone };
}
