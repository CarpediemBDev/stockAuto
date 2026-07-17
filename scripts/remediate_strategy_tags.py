# -*- coding: utf-8 -*-
"""SIMULATED 주문 strategy_type 오태깅 잔여 데이터 정합화 스크립트 (2026-07-17).

배경: scheduler/router_account의 SIMULATED 주문 경로가 strategy_type을 누락해
미체결 주문이 기본값(regime_switching)으로 오태깅됐고(코드 수정 완료:
docs/tasks/2026-07-16.md 참조), 그로 인해 오염된 데이터를 정리한다.

동작 (기본 dry-run, 실제 반영은 --apply):
1. 유저 설정 전략과 불일치한 보유(holdings)·매수 로그(trade_logs)를 설정 전략으로 재태깅.
   - core_satellite 등 복합 전략 유저는 슬롯 키가 설정값과 다른 것이 정상이므로 제외.
   - 재태깅 대상 (user_id, ticker, 설정전략) 보유가 이미 존재하면 유니크 제약 충돌이므로
     건너뛰고 수동 확인 대상으로 출력.
2. 유저 설정 전략과 불일치한 미체결 주문(unfilled_orders) 삭제.
   - 오태깅 매도는 체결 시점에 보유를 찾지 못해 어차피 삭제만 되며, 수정된
     스케줄러가 올바른 태그로 재발주하므로 삭제가 안전하다.

실행 전 반드시 stockauto.db 백업을 확보할 것.
사용: backend/venv/Scripts/python.exe scripts/remediate_strategy_tags.py [--apply]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "backend" / "stockauto.db"

# 복합(멀티 슬롯) 전략: 보유 태그가 설정값과 달라도 정상이므로 정합화 대상에서 제외
COMPOSITE_STRATEGIES = ("core_satellite", "multi_slot", "three_slot", "multi_slot_3")


def main() -> int:
    # Windows cp949 콘솔에서 유니코드 문자로 인한 UnicodeEncodeError 방지
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="실제로 DB에 반영 (기본은 dry-run)")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"[ERROR] DB 파일이 없습니다: {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH, timeout=15)
    c = conn.cursor()
    composite_ph = ",".join("?" for _ in COMPOSITE_STRATEGIES)

    # 1) 오귀속 보유 재태깅 대상
    mismatched_holdings = list(c.execute(
        f"""
        SELECT h.id, h.user_id, h.ticker, h.strategy_type, s.strategy_type, h.quantity
        FROM holdings h JOIN user_settings s ON s.user_id = h.user_id
        WHERE h.strategy_type != s.strategy_type
          AND s.strategy_type NOT IN ({composite_ph})
        """,
        COMPOSITE_STRATEGIES,
    ))

    retag_ids: list[tuple[int, str]] = []
    for h_id, user_id, ticker, wrong_tag, correct_tag, qty in mismatched_holdings:
        dup = c.execute(
            "SELECT id FROM holdings WHERE user_id=? AND ticker=? AND strategy_type=?",
            (user_id, ticker, correct_tag),
        ).fetchone()
        if dup:
            print(f"[SKIP] holding {h_id} (user {user_id} {ticker} x{qty}): "
                  f"{correct_tag} 태그 보유 {dup[0]}가 이미 존재 — 수동 병합 필요")
            continue
        print(f"[RETAG] holding {h_id}: user {user_id} {ticker} x{qty} {wrong_tag} -> {correct_tag}")
        retag_ids.append((h_id, correct_tag))

        logs = list(c.execute(
            "SELECT id FROM trade_logs WHERE user_id=? AND ticker=? AND strategy_type=?",
            (user_id, ticker, wrong_tag),
        ))
        for (log_id,) in logs:
            print(f"[RETAG] trade_log {log_id}: user {user_id} {ticker} {wrong_tag} -> {correct_tag}")
        if args.apply:
            c.execute("UPDATE holdings SET strategy_type=? WHERE id=?", (correct_tag, h_id))
            c.execute(
                "UPDATE trade_logs SET strategy_type=? WHERE user_id=? AND ticker=? AND strategy_type=?",
                (correct_tag, user_id, ticker, wrong_tag),
            )

    # 2) 오태깅 미체결 주문 삭제 대상
    stale_orders = list(c.execute(
        f"""
        SELECT o.id, o.user_id, o.ticker, o.trade_type, o.strategy_type, s.strategy_type
        FROM unfilled_orders o JOIN user_settings s ON s.user_id = o.user_id
        WHERE o.strategy_type != s.strategy_type
          AND s.strategy_type NOT IN ({composite_ph})
        """,
        COMPOSITE_STRATEGIES,
    ))
    for o_id, user_id, ticker, trade_type, wrong_tag, correct_tag in stale_orders:
        print(f"[DELETE] unfilled_order {o_id}: user {user_id} {ticker} {trade_type} "
              f"(태그 {wrong_tag}, 설정 {correct_tag})")
        if args.apply:
            c.execute("DELETE FROM unfilled_orders WHERE id=?", (o_id,))

    if args.apply:
        conn.commit()
        print(f"\n[DONE] 반영 완료: 보유 재태깅 {len(retag_ids)}건, 미체결 삭제 {len(stale_orders)}건")
    else:
        print(f"\n[DRY-RUN] 반영 예정: 보유 재태깅 {len(retag_ids)}건, 미체결 삭제 {len(stale_orders)}건 "
              f"— 실제 반영은 --apply")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
