import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
HARNESS_PATH = PROJECT_ROOT / "scripts" / "verify_harness.py"
SPEC = importlib.util.spec_from_file_location("stockauto_verify_harness", HARNESS_PATH)
assert SPEC is not None and SPEC.loader is not None
verify_harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_harness)


def complete_record(documentation: str) -> str:
    return f"""# 일자별 현황판

### 변경 영향 기록
- 변경 분류: `API 계약`
- 생산자: `backend/app/scanner/router.py`
- 소비자: `/scanner/latest`, `frontend/components/ManualWatchList.tsx`
- 데이터 경계: 공용 신호와 현재 사용자 관심종목을 응답에서 결합
- API 계약: 인증된 현재 사용자의 관심종목만 반환
- 문서 반영: {documentation}
- 회귀 테스트: 두 사용자 API 격리 테스트
- 미해결 위험: GitHub #8 추적 중
- 인수인계: 스캐너 데이터 계약 문서부터 확인
"""


def write_task(root: Path, content: str) -> str:
    task_path = root / "docs" / "tasks" / "2026-06-21.md"
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text(content, encoding="utf-8")
    return "docs/tasks/2026-06-21.md"


def test_non_contract_change_does_not_require_impact_record(tmp_path):
    errors = verify_harness.validate_change_contract(
        tmp_path,
        ["docs/tasks/2026-06-21.md"],
    )

    assert errors == []


def test_contract_change_requires_daily_task_file(tmp_path):
    errors = verify_harness.validate_change_contract(
        tmp_path,
        ["backend/app/scanner/router.py"],
    )

    assert any("docs/tasks/YYYY-MM-DD.md" in error for error in errors)


def test_contract_change_requires_complete_impact_record(tmp_path):
    task_path = write_task(
        tmp_path,
        "# 일자별 현황판\n\n### 변경 영향 기록\n- 변경 분류: `API 계약`\n",
    )

    errors = verify_harness.validate_change_contract(
        tmp_path,
        ["backend/app/scanner/router.py", task_path, "docs/API_STANDARD.md"],
    )

    assert any("필수 항목" in error for error in errors)
    assert any("생산자" in error for error in errors)


def test_contract_change_accepts_complete_record_and_long_lived_doc(tmp_path):
    task_path = write_task(
        tmp_path,
        complete_record("`docs/SCANNER_DATA_FLOW.md`"),
    )

    errors = verify_harness.validate_change_contract(
        tmp_path,
        [
            "backend/app/scanner/router.py",
            task_path,
            "docs/SCANNER_DATA_FLOW.md",
        ],
    )

    assert errors == []


def test_contract_change_without_doc_requires_explicit_reason(tmp_path):
    task_path = write_task(
        tmp_path,
        complete_record("`docs/SCANNER_DATA_FLOW.md`"),
    )

    errors = verify_harness.validate_change_contract(
        tmp_path,
        ["backend/app/scanner/router.py", task_path],
    )

    assert any("장기 문서" in error for error in errors)

    write_task(
        tmp_path,
        complete_record("영향 없음 - 기존 계약을 바꾸지 않는 내부 이름 정리"),
    )
    assert verify_harness.validate_change_contract(
        tmp_path,
        ["backend/app/scanner/router.py", task_path],
    ) == []
