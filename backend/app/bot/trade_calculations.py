import math
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_DOWN, ROUND_HALF_UP
from app.core.config import settings


@dataclass(frozen=True)
class RealizedPnL:
    buy_gross: Decimal
    buy_fee: Decimal
    sell_gross: Decimal
    sell_fee: Decimal
    sec_fee: Decimal
    net_revenue: Decimal
    realized_pnl: Decimal
    return_rate: Decimal
    return_rate_on_cost: Decimal
    return_rate_on_gross: Decimal


def to_decimal(val) -> Decimal:
    """금융 연산 경계면에서 모든 float/int/None 값을 안전하게 Decimal로 변환합니다."""
    if val is None:
        return Decimal('0.0000')
    if isinstance(val, Decimal):
        return val
    # float의 지수 표기법 등을 감안해 문자열을 거쳐 변환합니다.
    return Decimal(str(val))


def fee_rate_for_trade_mode(trade_mode: str | None) -> Decimal:
    rate = (
        settings.SIMULATED_FEE_RATE
        if (trade_mode or "SIMULATED").upper() == "SIMULATED"
        else settings.KIS_FEE_RATE
    )
    return to_decimal(rate).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


def calculate_buy_total(price: float | Decimal, quantity: int, fee_rate: float | Decimal) -> tuple[Decimal, Decimal, Decimal]:
    dec_price = to_decimal(price)
    dec_qty = to_decimal(quantity)
    dec_fee_rate = to_decimal(fee_rate)

    gross = (dec_price * dec_qty).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    fee = (gross * dec_fee_rate).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    total = (gross + fee).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    return gross, fee, total


def calculate_realized_pnl(
    avg_price: float | Decimal,
    filled_price: float | Decimal,
    quantity: int,
    fee_rate: float | Decimal,
    sec_fee_rate: float | Decimal = settings.SEC_FEE_RATE,
) -> RealizedPnL:
    dec_avg_price = to_decimal(avg_price)
    dec_filled_price = to_decimal(filled_price)
    dec_qty = to_decimal(quantity)
    dec_fee_rate = to_decimal(fee_rate)
    dec_sec_fee_rate = to_decimal(sec_fee_rate)

    buy_gross = (dec_avg_price * dec_qty).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    buy_fee = (buy_gross * dec_fee_rate).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    sell_gross = (dec_filled_price * dec_qty).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    sell_fee = (sell_gross * dec_fee_rate).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    sec_fee = (sell_gross * dec_sec_fee_rate).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    net_revenue = (sell_gross - sell_fee - sec_fee).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    realized_pnl = (net_revenue - (buy_gross + buy_fee)).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

    buy_total_cost = (buy_gross + buy_fee).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    if buy_total_cost > 0:
        return_rate_on_cost = ((realized_pnl / buy_total_cost) * Decimal('100.0')).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    else:
        return_rate_on_cost = Decimal('0.0000')

    if buy_gross > 0:
        return_rate_on_gross = ((realized_pnl / buy_gross) * Decimal('100.0')).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    else:
        return_rate_on_gross = Decimal('0.0000')

    return RealizedPnL(
        buy_gross=buy_gross,
        buy_fee=buy_fee,
        sell_gross=sell_gross,
        sell_fee=sell_fee,
        sec_fee=sec_fee,
        net_revenue=net_revenue,
        realized_pnl=realized_pnl,
        return_rate=return_rate_on_cost,
        return_rate_on_cost=return_rate_on_cost,
        return_rate_on_gross=return_rate_on_gross,
    )


def calculate_avg_price(old_avg: float | Decimal | None, old_qty: int, filled_price: float | Decimal, delta_qty: int) -> Decimal:
    dec_old_avg = to_decimal(old_avg)
    dec_old_qty = to_decimal(old_qty)
    dec_filled_price = to_decimal(filled_price)
    dec_delta_qty = to_decimal(delta_qty)
    new_qty = dec_old_qty + dec_delta_qty
    if new_qty == 0:
        return Decimal('0.0000')
    new_avg = ((dec_old_avg * dec_old_qty) + (dec_filled_price * dec_delta_qty)) / new_qty
    return new_avg.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


def calculate_profit_rate(current_price: float | Decimal, avg_price: float | Decimal) -> Decimal:
    dec_current_price = to_decimal(current_price)
    dec_avg_price = to_decimal(avg_price)
    if dec_avg_price == 0:
        return Decimal('0.0000')
    rate = ((dec_current_price - dec_avg_price) / dec_avg_price) * Decimal('100.0')
    return rate.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


def check_stop_loss_breach(profit_rate: float | Decimal, stop_loss_pct: float | Decimal | None) -> bool:
    if stop_loss_pct is None:
        return False
    dec_stop_loss_pct = to_decimal(stop_loss_pct)
    if dec_stop_loss_pct <= 0:
        return False
    dec_profit_rate = to_decimal(profit_rate)
    return dec_profit_rate <= -dec_stop_loss_pct


def check_trailing_stop_breach(
    current_price: float | Decimal,
    highest_price: float | Decimal,
    trailing_stop_pct: float | Decimal | None,
    avg_price: float | Decimal
) -> bool:
    if trailing_stop_pct is None:
        return False
    dec_trailing_stop_pct = to_decimal(trailing_stop_pct)
    if dec_trailing_stop_pct <= 0:
        return False

    dec_current_price = to_decimal(current_price)
    dec_highest_price = to_decimal(highest_price)
    dec_avg_price = to_decimal(avg_price)

    threshold = dec_highest_price * (Decimal('1.0') - dec_trailing_stop_pct / Decimal('100.0'))
    return dec_current_price <= threshold and dec_highest_price > dec_avg_price


# 롤링 박스 트레일링 스탑의 박스 길이는 '봉 개수'가 아니라 '시간 길이(분)'로 정의한다.
# 봉 개수로 두면 같은 값이 라이브(15분봉)와 백테스트(전략 인터벌)에서 서로 다른
# 실시간 길이를 뜻하게 되어, 백테스트 검증 결과가 라이브로 전이되지 않는다.
DEFAULT_ROLLING_BOX_MINUTES = 150      # 2.5시간 (15분봉 10개 — 기존 라이브 동작과 동일)
# 라이브 스캐너가 공급할 수 있는 상한. 이보다 긴 박스를 전략이 선언해도 라이브에서
# 데이터가 모자라 조용히 미발동되는 것을 막기 위해 환산 단계에서 잘라낸다.
MAX_ROLLING_BOX_MINUTES = 480          # 8시간
MIN_ROLLING_BOX_BARS = 2               # 1봉 박스는 직전 봉 저점과 같아 의미가 없다
LIVE_BOX_BAR_MINUTES = 15              # 라이브 스캐너가 박스 계산에 쓰는 봉 주기

# 백테스트 인터벌별 봉 1개의 길이(분). 1d는 정규장 6.5시간을 기준으로 한다.
_INTERVAL_BAR_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "1d": 390}


def bar_minutes_for_interval(interval: str) -> int:
    """백테스트 인터벌 문자열을 봉 1개의 길이(분)로 환산한다. 미지의 값은 60분으로 본다."""
    return _INTERVAL_BAR_MINUTES.get(interval, 60)


def resolve_rolling_box_bars(box_minutes: float, bar_minutes: int) -> int:
    """박스 길이(분)를 해당 타임프레임의 봉 개수로 환산한다.

    라이브와 백테스트가 같은 실시간 길이의 박스를 쓰도록 보장하는 단일 환산 지점이다.
    나눗셈이 딱 떨어지지 않으면 반올림(0.5는 올림)하며, 결과는 MIN_ROLLING_BOX_BARS
    이상으로 보정된다 — 예컨대 일봉에서는 2.5시간 박스를 표현할 수 없으므로 2봉이 된다.
    """
    if bar_minutes <= 0:
        raise ValueError("bar_minutes must be positive")
    minutes = min(max(float(box_minutes), 0.0), float(MAX_ROLLING_BOX_MINUTES))
    bars = int(math.floor(minutes / bar_minutes + 0.5))
    return max(MIN_ROLLING_BOX_BARS, bars)


def compute_box_low(recent_lows, bars: int) -> float | None:
    """완성 봉 저점 목록에서 최근 bars개의 최저값을 구한다. 순수 함수.

    봉이 bars개만큼 쌓이지 않았으면 None — 짧은 박스로 인한 조기 발동을 막는다.
    """
    if not recent_lows or bars <= 0:
        return None
    window = list(recent_lows)[-bars:]
    if len(window) < bars:
        return None
    try:
        numeric = [float(value) for value in window]
    except (TypeError, ValueError):
        return None
    if any(not math.isfinite(value) or value <= 0 for value in numeric):
        return None
    return min(numeric)


def compute_rolling_box_stop(
    prev_stop: float | Decimal | None,
    window_low: float | Decimal | None,
) -> Decimal:
    """롤링 박스 스탑 가격을 래칫(단조 증가) 조건으로 갱신합니다.

    새 스탑 = max(직전 스탑, 최근 N봉 저점). 윈도우 저점이 주가를 따라 내려가도
    스탑은 절대 후퇴하지 않는다 — 이 래칫이 없으면 하락 중 스탑이 주가를 쫓아
    내려가며 영원히 발동하지 않는 역주행이 발생한다(설계 핵심 불변식).
    """
    dec_prev = to_decimal(prev_stop)
    dec_window_low = to_decimal(window_low)
    return dec_prev if dec_prev >= dec_window_low else dec_window_low


def check_rolling_box_breach(
    current_price: float | Decimal,
    rolling_stop: float | Decimal | None,
    highest_price: float | Decimal,
    avg_price: float | Decimal,
) -> bool:
    """롤링 박스 스탑 이탈 여부를 판정합니다.

    ATR 트레일링과 동일하게 포지션이 한 번이라도 수익권(최고가 > 평단)에
    진입한 뒤에만 활성화된다 — 진입 직후 박스 하단이 평단 위에 있어
    즉시 청산되는 오발동을 차단하기 위함. 손실 방어는 기존 동적 손절선 담당.
    """
    dec_rolling_stop = to_decimal(rolling_stop)
    if dec_rolling_stop <= 0:
        return False
    dec_current_price = to_decimal(current_price)
    dec_highest_price = to_decimal(highest_price)
    dec_avg_price = to_decimal(avg_price)
    return dec_current_price < dec_rolling_stop and dec_highest_price > dec_avg_price


# ---------------------------------------------------------------------------
# 수확 모드 (Harvest Mode)
#
# 봇이 사지 않은 보유분(EXTERNAL)에 대해 "급등 후 꺾이면 판다"만 담당한다.
# 손절도, 시그널 붕괴 청산도 하지 않는다 - 위로 갔다가 꺾일 때만 작동한다.
#
# 앵커가 avg_price(사용자의 실제 매수가)가 아니라 observed_base_price(봇이 처음 본 가격)인
# 것이 이 모듈의 존재 이유다. 기존 트레일링·롤링박스는 highest_price > avg_price 가드에
# 걸려 반토막 종목에서 영원히 발동하지 않는다. 100달러에 사서 50달러까지 빠진 종목이
# 90달러까지 급등해도 본전을 넘긴 적이 없으므로 침묵한다 - 사용자가 원하는 바로 그 순간에.
# ---------------------------------------------------------------------------

HARVEST_ARM_BASE_PCT = 15.0     # 최소 무장 임계 - 이보다 작은 상승은 급등으로 보지 않는다
HARVEST_ARM_ATR_MULT = 4.0      # ATR 배수. 변동성이 큰 종목일수록 더 크게 올라야 급등이다
HARVEST_ARM_MAX_PCT = 40.0      # 상한. 이 이상을 요구하면 무장 자체가 사실상 불가능해진다
HARVEST_TRAILING_PCT = 5.0       # 트레일링 폭(고점 대비 %). 고정값이다 - get_harvest_trailing_pct 참조

# 노이즈 버퍼의 시간 하한. 사이클 수만으로는 주기 변동에 시간이 휘둘린다(실측 104~846초).
# 방어의 20분과 달리 짧게 잡는 이유는 역할이 다르기 때문이다 - 방어는 추세 붕괴가 실재하는지
# 확인하는 것이고, 수확은 순간적으로 찔렀다 돌아오는 꼬리만 걸러내면 된다. 오래 기다릴수록
# 급등분을 반납하므로 이 값을 키우는 것은 그 자체로 비용이다.
HARVEST_SUSTAIN_CYCLES = 2       # 최소 관측 횟수. 표본이 성긴 구간에서 한 번에 팔지 않는다
HARVEST_SUSTAIN_MINUTES = 2      # 최소 지속 시간(분). 주기가 빨라져도 이 값은 고정이다


# 봇 소유 포지션의 손절 노이즈 버퍼. 손절·트레일링·롤링박스 이탈에 공통으로 적용된다.
#
# 2회 관측 요구는 원래부터 있었고 여기서 바꾸지 않는다. 바뀌는 것은 그 대기가 사이클 수로만
# 세어지던 것을 벽시계 하한과 병행 게이트로 만든 것뿐이다. 사이클 실측 중앙값이 124초이므로
# 하한 2분은 현재 운영 동작과 사실상 같다 - 라이브 A/B 계정이 이 경로로 매매 중이라
# 동작을 바꾸는 것이 목적이 아니라 주기 변동에 흔들리지 않게 고정하는 것이 목적이다.
#
# 이 값을 키우면 손절이 늦어져 손실이 커진다. 노이즈 제거와 손실 확대의 맞바꿈이므로
# 꼬리 하나를 거르는 데 필요한 최소치만 잡는다.
EXIT_NOISE_BUFFER_CYCLES = 2     # 최소 관측 횟수 (기존 동작 유지)
EXIT_NOISE_BUFFER_MINUTES = 2    # 최소 지속 시간(분). 주기가 빨라져도 이 값은 고정이다


def _atr_pct(atr: float | Decimal | None, price: float | Decimal | None) -> Decimal:
    dec_atr = to_decimal(atr)
    dec_price = to_decimal(price)
    if dec_atr <= 0 or dec_price <= 0:
        return Decimal("0")
    return dec_atr / dec_price * Decimal("100")


def get_harvest_arm_pct(atr: float | Decimal | None, price: float | Decimal | None) -> float:
    """무장(감시 시작) 임계 상승률(%)을 ATR에 맞춰 계산합니다.

    고정값을 쓰면 안 된다 - 하루 10%씩 움직이는 종목에 +15%는 평범한 하루이고,
    잔잔한 대형주에 +40%는 도달하지 않는 숫자다. 상한을 두는 이유는 초고변동성
    종목에서 임계가 발산해 기능이 사실상 꺼지는 것을 막기 위함이다.
    """
    dynamic = _atr_pct(atr, price) * Decimal(str(HARVEST_ARM_ATR_MULT))
    value = max(Decimal(str(HARVEST_ARM_BASE_PCT)), dynamic)
    return float(min(value, Decimal(str(HARVEST_ARM_MAX_PCT))))


def get_harvest_trailing_pct() -> float:
    """수확 트레일링 폭(고점 대비 %). ATR과 무관한 고정값이다.

    예전에는 max(5%, ATR% x 2)였다. 스케줄러가 넘기는 ATR은 5분봉이라 평소에는 하한 5%로
    동작했지만, 급등하는 순간에는 ATR이 치솟아 폭이 20~60%로 부풀었다. 수확이 일하는 때가
    바로 그 순간이라 "고점에서 5% 꺾이면 판다"는 설계 의도가 정작 필요할 때 깨졌다
    (2026-09-24 HCTI는 폭 20.7%로 매도).

    고정 5%는 2026-09-26 시뮬레이션에서 채택했다. 최근 60일 급등·급등실패 56건(5분봉)과
    19건(1분봉, 2분 주기)에서 ATR 연동·고정 10/15%·상한·일봉 ATR·확인 단축보다 평균과
    중앙값이 고르게 나았다. 상세는 docs/plans/holding_management_modes.md 5.2절.
    """
    return HARVEST_TRAILING_PCT


def check_harvest_arm(
    current_price: float | Decimal,
    observed_base_price: float | Decimal | None,
    arm_pct: float | Decimal,
) -> bool:
    """관측 시작가 대비 급등해 무장 조건을 만족했는지 판정합니다."""
    dec_base = to_decimal(observed_base_price)
    if dec_base <= 0:
        return False
    threshold = dec_base * (Decimal("1.0") + to_decimal(arm_pct) / Decimal("100.0"))
    return to_decimal(current_price) > threshold


def check_harvest_breach(
    current_price: float | Decimal,
    highest_price: float | Decimal,
    trailing_pct: float | Decimal | None,
    observed_base_price: float | Decimal | None,
) -> bool:
    """수확 매도 조건(고점 대비 이탈)을 판정합니다.

    하한 가드가 설계의 핵심 불변식이다 - 관측 시작가 이하에서는 절대 팔지 않는다.
    무장이 래치(한번 켜지면 유지)이므로 이 가드가 없으면 급등 후 폭락한 종목에서
    고점만 높게 남아 즉시 이탈 판정이 나고, "위로 갔다 꺾일 때만 판다"는 EXTERNAL의
    계약이 정면으로 뒤집힌다. 손실 구간 방어는 수확 모드의 책임이 아니다.

    라이브 스케줄러는 observed_base_price 자리에 get_harvest_floor_price의 결과(관측 시작가와
    수수료 포함 본전가 중 높은 값)를 넘긴다. 시그니처는 그대로 두고 호출부에서 하한만 올린다.
    """
    if trailing_pct is None:
        return False
    dec_trailing = to_decimal(trailing_pct)
    if dec_trailing <= 0:
        return False

    dec_current = to_decimal(current_price)
    dec_base = to_decimal(observed_base_price)
    if dec_base <= 0 or dec_current <= dec_base:
        return False

    dec_highest = to_decimal(highest_price)
    if dec_highest <= dec_base:
        return False

    threshold = dec_highest * (Decimal("1.0") - dec_trailing / Decimal("100.0"))
    return dec_current <= threshold


def get_harvest_floor_price(
    observed_base_price: float | Decimal | None,
    avg_price: float | Decimal | None,
    fee_rate: float | Decimal,
    sec_fee_rate: float | Decimal = settings.SEC_FEE_RATE,
) -> Decimal:
    """수확 매도 하한 = max(관측 시작가, 수수료 포함 본전가).

    수확은 "올라갔을 때 판다"는 기능이다. 관측 시작가만 하한으로 쓰면 매입가보다 한참 아래에서
    관측이 시작된 종목이 반등하다 꺾일 때 손실 확정 매도가 난다(2026-09-24 HCTI, 매입가 $1.49·
    관측가 $0.75·매도가 $1.20, 실현손실 -$1,374). 손실 구간은 방어 모드의 몫이다.

    본전가는 calculate_realized_pnl과 같은 비용 구조(매수 수수료, 매도 수수료, SEC fee)에서
    순손익이 0이 되는 가격이며, 하한을 낮춰 잡지 않도록 소수 넷째 자리에서 올림한다.
    판정은 check_harvest_breach의 엄격 부등식(current > floor)을 그대로 쓴다.

    평단을 모르면(0 이하) 0을 돌려준다. check_harvest_breach는 하한 0을 "판정 불가"로 보고
    False를 내므로, 매입가를 확인할 수 없는 보유분은 수확 매도를 하지 않는다(fail-closed).
    """
    dec_avg = to_decimal(avg_price)
    if dec_avg <= 0:
        return Decimal("0")
    dec_fee = to_decimal(fee_rate)
    dec_sec = to_decimal(sec_fee_rate)
    net_ratio = Decimal("1") - dec_fee - dec_sec
    if net_ratio <= 0:
        return Decimal("0")
    break_even = (dec_avg * (Decimal("1") + dec_fee) / net_ratio).quantize(
        Decimal("0.0001"), rounding=ROUND_CEILING
    )
    return max(to_decimal(observed_base_price), break_even)


# ---------------------------------------------------------------------------
# 방어 경보 (Defense Guard)
#
# "무너지면 알림" - 경보만 보내고 주문은 내지 않는다.
#
# 이 모듈에서 가장 중요한 결정은 절대 점수선을 쓰지 않는다는 것이다. -50% 물린 종목은
# 십중팔구 이미 시그널 점수가 붕괴선 아래이므로, 절대선으로 판정하면 방어를 켜는 순간
# 즉시 경보가 되어 "관측 시작 즉시 청산"이 이름만 바꿔 재현된다. 상태(state)가 아니라
# 전이(transition)를 본다 - 켠 시점을 기준선으로 박고 거기서 추가로 악화될 때만 울린다.
#
# 점수와 가격 두 조건을 모두 요구하는 이유도 같다. 점수만 보면 이미 바닥인 종목이 상시
# 발동하고, 신저가만 보면 정상 눌림에도 발동한다. 둘을 겹쳐야 "무너지는 중"이 잡힌다.
# ---------------------------------------------------------------------------

GUARD_SCORE_DROP_DELTA = 15.0   # 기준선 대비 이만큼 더 떨어져야 "추가 악화"로 본다
GUARD_GRACE_MINUTES = 30        # 켠 직후 오발동을 막는 유예기간
GUARD_ALERT_COOLDOWN_HOURS = 6  # 같은 종목에 경보를 반복하지 않는 간격


def compute_guard_low(
    prev_low: float | Decimal | None,
    observed_low: float | Decimal | None,
) -> Decimal:
    """방어 기준 저가를 래칫(단조 감소) 조건으로 갱신합니다.

    새 저가 = min(직전 저가, 관측 저가). 롤링 박스 스탑의 단조 증가 불변식을 방향만
    뒤집은 것이다. 래칫이 없으면 반등할 때 기준 저가가 따라 올라가 다음 하락에서
    "신저가"가 매번 참이 되고, 정상 등락이 전부 경보가 된다.

    prev_low가 없으면(최초 설정) 관측 저가를 그대로 기준선으로 삼는다.
    """
    dec_observed = to_decimal(observed_low)
    if prev_low is None:
        return dec_observed
    dec_prev = to_decimal(prev_low)
    if dec_prev <= 0:
        return dec_observed
    if dec_observed <= 0:
        return dec_prev
    return dec_observed if dec_observed < dec_prev else dec_prev


def check_guard_breach(
    current_score: float | Decimal | None,
    baseline_score: float | Decimal | None,
    current_price: float | Decimal,
    baseline_low: float | Decimal | None,
    score_drop_delta: float | Decimal = GUARD_SCORE_DROP_DELTA,
) -> bool:
    """방어 경보 발동 여부를 판정합니다. 두 조건을 모두 만족해야 참입니다.

    1. 시그널 점수가 켠 시점보다 delta 이상 더 떨어졌다 (추가 악화)
    2. 현재가가 켠 이후 관측 저가 아래로 내려갔다 (신저가 갱신)

    어느 한쪽만으로는 판정하지 않는다. 점수 단독은 이미 나쁜 종목에서 상시 참이고,
    가격 단독은 하락 추세의 평범한 눌림에서도 참이다.
    """
    if current_score is None or baseline_score is None or baseline_low is None:
        return False

    dec_baseline_low = to_decimal(baseline_low)
    if dec_baseline_low <= 0:
        return False

    score_worsened = to_decimal(current_score) <= (
        to_decimal(baseline_score) - to_decimal(score_drop_delta)
    )
    if not score_worsened:
        return False

    return to_decimal(current_price) < dec_baseline_low


# 방어 조치(자동 청산)의 추가 가드. 경보보다 훨씬 보수적이어야 한다 - 경보의 최악은
# 헛울림이지만 청산의 최악은 되돌릴 수 없는 손실 확정이다.
# 조치 게이트는 사이클 수와 실제 경과 시간을 모두 요구한다.
#
# 사이클 수만 쓰면 시간적으로 불안정하다. 스케줄러는 1분 간격으로 등록돼 있지만 사이클이
# 1분 안에 끝나지 않으면 겹치는 실행이 건너뛰어져, 실측 중앙값이 124초이고 편차가 104~846초다
# (2026-09-06 admin action_logs 40표본). 그래서 "10사이클"이 20분일 수도 두 시간일 수도 있다.
# 되돌릴 수 없는 매도의 조건이 그렇게 흔들려서는 안 된다.
#
# 반대로 시간만 쓰면 관측이 성기게 들어온 구간에서 한두 번의 판정으로 조치가 나갈 수 있다.
# 둘을 모두 요구해야 "충분히 여러 번, 충분히 오래 확인했다"가 성립한다.
#
# 다만 두 조건의 역할은 대등하지 않다. **시간이 게이트를 주도하고 횟수는 하한만 준다.**
# 처음에는 횟수를 10으로 두었는데, 주기가 느려지자 횟수가 시간을 압도했다. 2026-09 W37 NY
# 정규장의 사이클 간격 중앙값이 426초라 10사이클은 약 71분이었다. 화면은 "20분 넘게
# 이어지면"이라고 말하는데 실제로는 한 시간이 넘게 걸린 셈이다. 사용자가 믿고 켜는 조건이
# 사이클 주기라는 보이지 않는 변수에 따라 3배 이상 늘어나서는 안 된다.
#
# 하한 3은 "한두 번의 판정으로는 나가지 않는다"를 지키는 최소값이다. 정규장 주기에서 20분이면
# 대략 세 번 관측되므로 이 하한은 평소에는 시간 조건과 거의 동시에 충족되고, 주기가 극단적으로
# 느려진 경우에만 추가로 대기를 늘린다.
GUARD_SUSTAIN_CYCLES = 3           # 최소 연속 충족 횟수(하한). 게이트는 아래 시간 조건이 주도한다
GUARD_SUSTAIN_MINUTES = 20         # 최소 지속 시간(분). 사이클 주기가 흔들려도 이 값은 고정이다
GUARD_ACTION_COOLDOWN_HOURS = 24   # 같은 보유분에 하루 한 번만 조치한다
GUARD_DEFAULT_SELL_RATIO = 0.5     # 부분 청산 기본 비율. 포지션 전체를 확정하지 않는다


def resolve_guard_sell_qty(quantity: int, sell_ratio: float | Decimal | None) -> int:
    """방어 조치로 매도할 수량을 구한다.

    비율을 곱해 내림하되 최소 1주는 보장하고, 보유 수량을 넘지 않는다. 1주 보유처럼
    비율로 나눌 수 없는 경우에도 조치가 조용히 미발동되지 않도록 하한을 둔다.
    """
    if quantity <= 0:
        return 0
    ratio = to_decimal(sell_ratio if sell_ratio is not None else GUARD_DEFAULT_SELL_RATIO)
    if ratio <= 0:
        return 0
    if ratio >= 1:
        return quantity
    qty = int((to_decimal(quantity) * ratio).to_integral_value(rounding=ROUND_DOWN))
    return max(1, min(qty, quantity))


# ---------------------------------------------------------------------------
# 갭상승 청산 (2026-10-04 A/B)
#
# 헬스케어 소형·페니주 53종목 일봉(2019~2026)에서 정규장 시가가 전일 종가보다 15% 이상
# 높게 열린 날은 시가→종가 중앙값이 학습 구간 -8.2%(n=219), 검증 구간 -8.4%(n=252)로
# 두 구간이 같은 방향이었다. 롱 전용 시스템은 이 하락을 공매도로 먹을 수 없으므로
# "들고 있던 종목이 갭상승하면 그날 판다"는 청산 규칙으로만 쓴다.
#
# 갭은 정규장 기준이어야 한다. 프리마켓 첫 체결가로 재면 리서치와 다른 값을 보게 된다.
# ---------------------------------------------------------------------------

GAP_EXIT_THRESHOLD_PCT = 15.0


def compute_session_gap_pct(
    prev_close: float | Decimal | None,
    session_open: float | Decimal | None,
) -> Decimal | None:
    """정규장 시가의 전일 종가 대비 갭(%)을 구한다. 계산할 수 없으면 None.

    0을 돌려주지 않고 None을 돌려주는 이유 - 시세를 못 받은 것과 갭이 없는 것을 구분해야
    호출부가 "판정 보류"와 "해당 없음"을 다르게 다룰 수 있다.
    """
    if prev_close is None or session_open is None:
        return None
    dec_prev = to_decimal(prev_close)
    dec_open = to_decimal(session_open)
    if dec_prev <= 0 or dec_open <= 0:
        return None
    return ((dec_open / dec_prev) - Decimal("1")) * Decimal("100")


def check_gap_exit(
    gap_pct: float | Decimal | None,
    threshold_pct: float | Decimal = GAP_EXIT_THRESHOLD_PCT,
) -> bool:
    """갭상승 청산 조건 충족 여부. 갭을 모르면(None) 거짓이다."""
    if gap_pct is None:
        return False
    dec_threshold = to_decimal(threshold_pct)
    if dec_threshold <= 0:
        return False
    return to_decimal(gap_pct) >= dec_threshold


# 목표비중형 자율 슬롯(canary_allocation)의 목표수량 버퍼. 수수료(0.10%)·지정가 여유(0.10%)·호가 변동을 덮는다.
# 0.98(기존 IN/OUT 경로 값)을 쓰면 BIL·IEF까지 포함한 전 비중의 2%가 놀아 연 약 0.3%p를 잃었다
# (2026-10-05 실데이터 패리티: 0.98 → CAGR 15.97%, 1.0 → 16.30%). 실제 매수는 집행부가 가용 현금으로 한 번 더 제한한다.
TARGET_WEIGHT_CASH_BUFFER = 0.995


def plan_target_weight_orders(
    total_value: float | Decimal,
    target_weights: dict[str, float],
    prices: dict[str, float | Decimal],
    current_qty: dict[str, int],
    cash_buffer: float = TARGET_WEIGHT_CASH_BUFFER,
) -> dict[str, int] | None:
    """목표비중 → 티커별 '차이 수량'(양수=매수, 음수=매도). 라이브 집행부와 백테스트가 공유한다.

    목표수량 = floor(총자산 × 비중 × 버퍼 / 가격). 목표에 없는 기존 보유 티커는 전량 매도 대상이다.
    목표 티커의 가격을 모르면 None(판단 보류) — 가격 없이 수량을 추정하지 않는다.
    """
    dec_total = to_decimal(total_value)
    if dec_total <= 0:
        return None
    buffer = to_decimal(cash_buffer)
    plan: dict[str, int] = {}
    for ticker, weight in target_weights.items():
        price = prices.get(ticker)
        if price is None or to_decimal(price) <= 0:
            return None
        budget = dec_total * to_decimal(weight) * buffer
        target_qty = int((budget / to_decimal(price)).to_integral_value(rounding=ROUND_DOWN))
        delta = target_qty - int(current_qty.get(ticker, 0) or 0)
        if delta:
            plan[ticker] = delta
    for ticker, qty in current_qty.items():
        if ticker not in target_weights and qty:
            plan[ticker] = -int(qty)
    return plan
