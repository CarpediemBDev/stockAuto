"""SIMULATED 계좌 입출금 등록 운영 스크립트.

사용법:
    backend/venv/Scripts/python.exe scripts/sim_cash_transfer.py <username> <금액(원)> "<메모>"
    backend/venv/Scripts/python.exe scripts/sim_cash_transfer.py admin 10000000 "HCTI 입고 자금"
    backend/venv/Scripts/python.exe scripts/sim_cash_transfer.py admin --list

금액이 음수면 출금이다. 입금한 계정은 단순 수익률이 희석되므로 전략 성과 비교에서 제외한다.
등록 직후 잔고 스냅샷을 새로 저장해 대시보드가 낡은 값을 보이지 않게 한다.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.brokers.broker_factory import get_broker_client  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.models import SimCashTransfer, User, UserSettings  # noqa: E402
from app.trades.equity_snapshot import record_equity_snapshot  # noqa: E402
from app.trades.sim_cash import SimCashTransferError, record_sim_cash_transfer  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    username = argv[0]
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            print(f"ERROR: 사용자 {username}가 없습니다.")
            return 1

        if argv[1] == "--list":
            rows = db.query(SimCashTransfer).filter(SimCashTransfer.user_id == user.id).order_by(SimCashTransfer.id).all()
            for r in rows:
                print(f"#{r.id} {r.created_at} {float(r.amount_krw):+,.0f}원 {r.memo or ''}")
            print(f"합계 {sum(float(r.amount_krw) for r in rows):+,.0f}원 ({len(rows)}건)")
            return 0

        memo = argv[2] if len(argv) > 2 else None
        try:
            row = record_sim_cash_transfer(db, user.id, argv[1], memo)
        except (SimCashTransferError, ArithmeticError, ValueError) as exc:
            print(f"ERROR: {exc}")
            return 1
        print(f"OK: #{row.id} {username} {float(row.amount_krw):+,.0f}원 ({memo or '메모 없음'})")

        settings_row = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
        balance = get_broker_client(settings_row).get_account_balance()
        record_equity_snapshot(user.id, "SIMULATED", balance, None, True)
        print(
            f"잔고: 총자산 {balance['total_asset']:,}원, 현금 {balance['cash_balance']:,}원, "
            f"손익 {balance['profit_loss']:,}원 ({balance['profit_rate']:+.2f}%)"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
