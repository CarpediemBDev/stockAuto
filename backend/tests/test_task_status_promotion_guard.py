"""verify_harness.check_task_status_promotion 회귀 테스트.

2026-07-23 사고: 이전 세션이 사용자 승인 없이 태스크를 [x]로 자체 승격했다.
이 가드가 [R]/[/]/[ ] → [x] 승격과 신규 [x] 등록을 차단하고,
정상 전이와 APPROVED 마커는 통과시키는지 고정한다.
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[2]
HARNESS_PATH = PROJECT_ROOT / "scripts" / "verify_harness.py"
SPEC = importlib.util.spec_from_file_location("stockauto_verify_harness_task", HARNESS_PATH)
assert SPEC is not None and SPEC.loader is not None
verify_harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_harness)


TASK_REL = "docs/tasks/2026-07-23.md"


def setup_case(tmp_path, monkeypatch, before: str, after: str):
    """before=HEAD 버전, after=작업트리 버전으로 가드 실행 환경을 만든다."""
    task_path = tmp_path / TASK_REL
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text(after, encoding="utf-8")

    monkeypatch.setattr(
        verify_harness, "get_changed_files", lambda root: [TASK_REL]
    )
    monkeypatch.setattr(verify_harness, "base_ref_for_diff", lambda: "HEAD")

    def fake_git_show(root, ref, rel_path):
        if before is None:
            return None
        return before

    monkeypatch.setattr(verify_harness, "git_show", fake_git_show)


def board(*lines: str) -> str:
    return "# 2026-07-23 Task Board\n\n## 신규 작업\n" + "\n".join(lines) + "\n"


def test_flags_r_to_x_promotion(tmp_path, monkeypatch):
    setup_case(
        tmp_path, monkeypatch,
        before=board("- [R] 스캐너 캐시 고착 수정"),
        after=board("- [x] 스캐너 캐시 고착 수정"),
    )
    assert verify_harness.check_task_status_promotion(tmp_path) is False


def test_flags_in_progress_to_x_promotion(tmp_path, monkeypatch):
    setup_case(
        tmp_path, monkeypatch,
        before=board("- [/] 스캐너 캐시 고착 수정"),
        after=board("- [x] 스캐너 캐시 고착 수정"),
    )
    assert verify_harness.check_task_status_promotion(tmp_path) is False


def test_flags_new_item_born_as_x(tmp_path, monkeypatch):
    setup_case(
        tmp_path, monkeypatch,
        before=board("- [R] 기존 작업"),
        after=board("- [R] 기존 작업", "- [x] 등록도 안 하고 완료 표기한 작업"),
    )
    assert verify_harness.check_task_status_promotion(tmp_path) is False


def test_allows_normal_transition(tmp_path, monkeypatch):
    setup_case(
        tmp_path, monkeypatch,
        before=board("- [ ] 스캐너 캐시 고착 수정"),
        after=board("- [/] 스캐너 캐시 고착 수정"),
    )
    assert verify_harness.check_task_status_promotion(tmp_path) is True


def test_allows_x_with_approval_marker(tmp_path, monkeypatch):
    setup_case(
        tmp_path, monkeypatch,
        before=board("- [R] 스캐너 캐시 고착 수정"),
        after=board("- [x] 스캐너 캐시 고착 수정 <!-- APPROVED: 2026-07-23 사용자 승인 -->"),
    )
    assert verify_harness.check_task_status_promotion(tmp_path) is True


def test_ignores_x_already_present_in_head(tmp_path, monkeypatch):
    """HEAD에 이미 [x]였던 항목은 이번 diff의 전이가 아니므로 통과."""
    setup_case(
        tmp_path, monkeypatch,
        before=board("- [x] 이전 세션에서 이미 완료된 작업"),
        after=board("- [x] 이전 세션에서 이미 완료된 작업", "- [/] 새 작업"),
    )
    assert verify_harness.check_task_status_promotion(tmp_path) is True


def test_passes_when_no_task_file_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(
        verify_harness, "get_changed_files", lambda root: ["scripts/verify_harness.py"]
    )
    assert verify_harness.check_task_status_promotion(tmp_path) is True
