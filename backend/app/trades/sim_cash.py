"""SIMULATED 계좌 입출금 원장(sim_cash_transfers) 등록.

잔고 계산은 LocalSimulatedBroker.get_account_balance 한 곳이 이 원장을 읽는다. 여기는 기록만 한다.
실계좌(KIS·Toss)는 증권사가 잔고를 계산하므로 입출금을 기록할 곳이 아니다 - 그래서 SIMULATED
사용자에게만 허용한다.
"""
from decimal import Decimal

from app.core.models import SimCashTransfer, User, UserSettings


class SimCashTransferError(ValueError):
    """입출금을 기록할 수 없는 요청."""


def record_sim_cash_transfer(db, user_id: int, amount_krw, memo: str | None = None) -> SimCashTransfer:
    """입금(+) 또는 출금(-)을 원장에 한 건 기록하고 커밋한다.

    출금은 현금이 음수가 되는지 검사하지 않는다. 잔고 계산이 음수 현금을 0으로 자르므로
    화면이 틀어지지는 않지만, 호출자가 현재 현금을 확인한 뒤 출금해야 한다.
    """
    amount = Decimal(str(amount_krw))
    if amount == 0:
        raise SimCashTransferError("금액이 0이면 기록하지 않습니다.")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise SimCashTransferError(f"사용자 {user_id}가 없습니다.")
    settings_row = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    trade_mode = ((settings_row.trade_mode if settings_row else None) or "SIMULATED").upper()
    if trade_mode != "SIMULATED":
        raise SimCashTransferError(
            f"{user.username}는 {trade_mode} 모드입니다. 입출금 원장은 SIMULATED 계좌 전용입니다."
        )

    row = SimCashTransfer(user_id=user_id, amount_krw=amount, memo=memo)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
