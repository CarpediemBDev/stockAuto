# -*- coding: utf-8 -*-
"""라이브 신호 필드 계약 상시 가드.

전략 클래스는 백테스트 엔진이 만드는 이름으로 지표를 읽는다. 라이브 스캐너가 그
이름으로 값을 싣지 않으면 `BaseStrategy._safe_get`이 예외 없이 0을 돌려주고, 전략은
에러 한 줄 없이 '진입 조건 미충족'으로 퇴화한다. 로그에도 안 남아 "오늘은 살 종목이
없네"와 구분되지 않는다(2026-08-23 실측: 95종 중 74종이 이 상태였다).

이 가드는 그 침묵 실패를 컴파일 타임에 드러낸다. 전략이 읽는 모든 필드는 반드시
셋 중 하나로 분류돼 있어야 한다:

  1. LIVE_SIGNAL_KEYS       — 라이브가 실제로 싣는 필드
  2. UNSUPPORTED_LIVE_FIELDS — 외부 데이터가 없어 라이브에서 원리상 불가
  3. PENDING_LIVE_FIELDS     — 계산은 가능하나 아직 미구현(백로그)

어디에도 없는 필드가 나타나면 새로운 드리프트이므로 반려한다.
앱을 import하지 않고 AST로만 검사하므로 .env나 DB 없이도 동작한다.

사용법: python scripts/check_signal_field_contract.py [repo_root]
"""

import ast
import re
import sys
from pathlib import Path

CONTRACT_MODULE = Path("backend") / "app" / "scanner" / "signal_contract.py"
SCANNER_MODULE = Path("backend") / "app" / "scanner" / "scanner.py"
STRATEGY_DIR = Path("backend") / "app" / "strategies"
METRICS_MODULE = Path("backend") / "app" / "scanner" / "indicator_metrics.py"

# metrics['이름'] = 리터럴 대입이 아니라 헬퍼가 동적으로 붙이는 컬럼.
# 정적 수집에 안 잡히므로 여기에 명시한다(app/scanner/indicators.py의
# calculate_double_bb_reversion_signals가 생산).
DYNAMIC_METRIC_FIELDS = frozenset({"is_double_bb_buy", "is_double_bb_sell"})

# 전략이 지표를 읽는 유일한 통로.
FIELD_READ_PATTERN = re.compile(r"_safe_get\(row,\s*'([A-Za-z0-9_]+)'")


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _module_assignments(tree: ast.Module) -> dict:
    """모듈 최상위 대입문을 {이름: 값 노드}로 모은다."""
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value
    return out


def _string_constants(node: ast.AST) -> set:
    """노드 아래의 모든 문자열 상수를 모은다(frozenset/tuple/dict 값 공용)."""
    return {
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    }


def _declared_sets(root: Path) -> tuple:
    """signal_contract.py에서 선언 집합 3종과 표준 필드를 AST로 읽는다."""
    assignments = _module_assignments(_parse(root / CONTRACT_MODULE))
    missing = [
        name
        for name in ("LIVE_SIGNAL_KEYS", "UNSUPPORTED_LIVE_FIELDS",
                     "PENDING_LIVE_FIELDS", "CANONICAL_FIELDS",
                     "LIVE_ONLY_FIELDS")
        if name not in assignments
    ]
    if missing:
        raise SystemExit(f"  [FAIL] signal_contract.py에 선언이 없습니다: {', '.join(missing)}")

    live = _string_constants(assignments["LIVE_SIGNAL_KEYS"])
    canonical = _string_constants(assignments["CANONICAL_FIELDS"])
    # 그룹 딕셔너리는 키가 한글 사유 설명이므로, 값(튜플) 쪽 문자열만 필드로 취급한다.
    unsupported, pending = set(), set()
    for name, bucket in (("UNSUPPORTED_LIVE_FIELDS", unsupported),
                         ("PENDING_LIVE_FIELDS", pending)):
        node = assignments[name]
        if not isinstance(node, ast.Dict):
            raise SystemExit(f"  [FAIL] {name}은 사유별 딕셔너리여야 합니다.")
        for value in node.values:
            bucket |= _string_constants(value)
    live_only = _string_constants(assignments["LIVE_ONLY_FIELDS"])
    return live, canonical, unsupported, pending, live_only


def _scanner_detail_keys(root: Path, canonical: set) -> set:
    """scanner.py의 'details' 딕셔너리 리터럴이 실제로 싣는 키를 수집한다."""
    keys = set()
    for node in ast.walk(_parse(root / SCANNER_MODULE)):
        if not isinstance(node, ast.Dict):
            continue
        for outer_key, outer_value in zip(node.keys, node.values):
            is_details = (
                isinstance(outer_key, ast.Constant)
                and outer_key.value == "details"
                and isinstance(outer_value, ast.Dict)
            )
            if not is_details:
                continue
            for key, value in zip(outer_value.keys, outer_value.values):
                if key is None:
                    # `**build_canonical_metrics(...)` 병합 — 표준 필드가 통째로 실린다.
                    if "build_canonical_metrics" in ast.dump(value):
                        keys |= canonical
                elif isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.add(key.value)
    return keys


def _backtest_metric_fields(root: Path) -> set:
    """indicator_metrics.py가 만드는 지표 이름을 AST로 수집한다.

    metrics['이름'] = ... 형태의 대입만 센다. 동적으로 컬럼을 붙이는 헬퍼
    (calculate_double_bb_reversion_signals 등)는 여기서 보이지 않으므로,
    그 산출물은 signal_contract의 LIVE_ONLY_FIELDS나 결손 선언으로 다루지 말고
    이 함수의 예외 목록에 적어 둔다.
    """
    produced = set(DYNAMIC_METRIC_FIELDS)
    for node in ast.walk(_parse(root / METRICS_MODULE)):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "metrics"
                    and isinstance(target.slice, ast.Constant)
                    and isinstance(target.slice.value, str)):
                produced.add(target.slice.value)
    return produced


def _strategy_fields(root: Path) -> dict:
    """전략 파일별로 읽는 필드 집합을 모은다."""
    out = {}
    for path in sorted((root / STRATEGY_DIR).glob("*.py")):
        if path.stem in ("__init__", "base_strategy", "strategy_factory", "strategy_catalog"):
            continue
        fields = set(FIELD_READ_PATTERN.findall(path.read_text(encoding="utf-8")))
        if fields:
            out[path.stem] = fields
    return out


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    live, canonical, unsupported, pending, live_only = _declared_sets(root)
    actual = _scanner_detail_keys(root, canonical)
    strategy_fields = _strategy_fields(root)
    backtest_fields = _backtest_metric_fields(root)
    all_read = set().union(*strategy_fields.values()) if strategy_fields else set()

    errors = []

    # (1) 선언과 실제 스캐너 산출이 어긋나면 계약 자체가 거짓말이 된다.
    undeclared = actual - live
    if undeclared:
        errors.append(
            "스캐너가 싣지만 LIVE_SIGNAL_KEYS에 없는 키: "
            + ", ".join(sorted(undeclared))
        )
    phantom = live - actual
    if phantom:
        errors.append(
            "LIVE_SIGNAL_KEYS에 선언됐으나 스캐너가 싣지 않는 키: "
            + ", ".join(sorted(phantom))
        )

    # (2) 어느 집합에도 분류되지 않은 필드 = 새 드리프트.
    classified = live | unsupported | pending
    for strategy, fields in sorted(strategy_fields.items()):
        unknown = fields - classified
        if unknown:
            errors.append(
                f"{strategy}: 미분류 필드 {', '.join(sorted(unknown))} "
                "(라이브에 싣거나 UNSUPPORTED/PENDING에 사유와 함께 선언하세요)"
            )

    # (3) 이미 라이브에 실리는데 아직 결손으로 선언된 필드 = 노후 선언.
    stale = (unsupported | pending) & live
    if stale:
        errors.append(
            "라이브에 이미 실리는데 결손으로 남은 선언(제거 필요): " + ", ".join(sorted(stale))
        )

    # (3-b) 역방향 결손: 라이브는 싣는데 백테스트 지표가 만들지 않는 필드.
    # 이 경우 같은 전략이 라이브와 백테스트에서 서로 다른 조건으로 돌아가고,
    # 백테스트 성적을 라이브의 예측치로 쓸 수 없게 된다. 앞의 (1)~(3)은 전부
    # "라이브가 백테스트보다 적게 받는" 방향만 보므로 여기서 반대편을 막는다.
    backtest_missing = (all_read & live) - backtest_fields - live_only
    if backtest_missing:
        owners = sorted(
            strategy
            for strategy, fields in strategy_fields.items()
            if fields & backtest_missing
        )
        errors.append(
            "라이브에는 실리지만 백테스트 지표가 만들지 않는 필드: "
            + ", ".join(sorted(backtest_missing))
            + f" (영향 전략: {', '.join(owners)}) "
            "(indicator_metrics.py에 계산을 추가하거나 LIVE_ONLY_FIELDS에 사유와 함께 선언하세요)"
        )

    # (3-c) 백테스트가 이미 만드는데 라이브 전용으로 선언된 필드 = 노후 선언.
    stale_live_only = live_only & backtest_fields
    if stale_live_only:
        errors.append(
            "백테스트가 이미 만드는데 LIVE_ONLY_FIELDS에 남은 선언(제거 필요): "
            + ", ".join(sorted(stale_live_only))
        )

    # (4) 어떤 전략도 읽지 않는 선언 = 사문화된 목록.
    orphan = (unsupported | pending | live_only) - all_read
    if orphan:
        errors.append(
            "어떤 전략도 읽지 않는 결손 선언(제거 필요): " + ", ".join(sorted(orphan))
        )

    if errors:
        print("[FAIL] 라이브 신호 필드 계약 위반")
        for error in errors:
            print(f"  - {error}")
        return 1

    blocked = sorted(
        name for name, fields in strategy_fields.items()
        if fields & (unsupported | pending)
    )
    print(
        f"[OK] 신호 필드 계약 정합. 라이브 {len(live)}키 / 전략이 읽는 필드 {len(all_read)}종 "
        f"(미구현 {len(pending & all_read)}, 불가 {len(unsupported & all_read)})"
    )
    # 콘솔 코드페이지(cp949)에서 인코딩할 수 없는 문자는 쓰지 않는다.
    print(f"     라이브 미지원 필드에 의존하는 전략 {len(blocked)}종: 카탈로그 노출 정리 대상")
    return 0


if __name__ == "__main__":
    sys.exit(main())
