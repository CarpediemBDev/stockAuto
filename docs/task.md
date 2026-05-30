# 🔧 시니어 코드 리뷰 지적사항 일괄 수정 (2026-05-30)

## 🔴 CRITICAL

- [x] **1. 설정 페이지 확인 모달 3개 복원** — `showRealWarning`, `showResetModal`, `showLiquidateModal` 렌더링 JSX 추가
- [x] **2. 타임존 불일치 수정** — `datetime.now()` → `datetime.now(timezone.utc)` 쿨다운 비교 UTC 정합성 복원
- [x] **3. `is_processing` 레이스 컨디션 방지** — `threading.Lock()` 추가하여 읽기-쓰기 원자성 보장
- [x] **4. KIS 브로커 체결 확인 로직** — `_confirm_fill()` 폴링 메서드 추가 (최대 5회 × 2초, fallback 보장)

## 🟠 HIGH

- [x] **5. `force-liquidate` 수수료 반영 + 롤백** — KIS_FEE_RATE/SEC_FEE_RATE 차감 + except에 db.rollback()
- [x] **6. 비상승장 S1 점수 반영 수정** — `final_score = 0` → `final_score = cand['s1_score']`
- [x] **7. asyncio 이벤트 루프 안정화** — `asyncio.run()` 우선 사용, ensure_future fallback 구조로 변경
- [x] **8. bare except → except Exception** — scanner.py 내 3곳 수정 완료
