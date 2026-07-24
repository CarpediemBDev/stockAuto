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


def test_merge_does_not_flag_x_arriving_from_other_parent(tmp_path, monkeypatch):
    """병합 중 MERGE_HEAD(main)에서 이미 승인·커밋된 [x]는 오탐하지 않는다.

    실제 사고: feat 브랜치에 origin/main을 병합할 때, main에서 승인 완료된 남의
    [x] 항목이 HEAD 기준으로는 '신규 [x]'로 보여 잘못 차단됐다.
    """
    task_path = tmp_path / TASK_REL
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text(
        board("- [x] 남의 세션이 main에서 승인받아 완료한 작업", "- [R] 내 작업"),
        encoding="utf-8",
    )

    monkeypatch.setattr(verify_harness, "get_changed_files", lambda root: [TASK_REL])
    monkeypatch.setattr(
        verify_harness, "base_refs_for_task_diff", lambda root: ["HEAD", "MERGE_HEAD"]
    )

    def fake_git_show(root, ref, rel_path):
        if ref == "HEAD":  # 내 브랜치: 남의 항목이 아직 없음
            return board("- [R] 내 작업")
        return board("- [x] 남의 세션이 main에서 승인받아 완료한 작업")  # MERGE_HEAD

    monkeypatch.setattr(verify_harness, "git_show", fake_git_show)

    assert verify_harness.check_task_status_promotion(tmp_path) is True


def test_merge_still_blocks_genuine_self_promotion(tmp_path, monkeypatch):
    """병합 중이라도 어느 부모에도 [x]가 아니었던 항목의 승격은 여전히 차단한다."""
    task_path = tmp_path / TASK_REL
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text(board("- [x] 내 작업"), encoding="utf-8")

    monkeypatch.setattr(verify_harness, "get_changed_files", lambda root: [TASK_REL])
    monkeypatch.setattr(
        verify_harness, "base_refs_for_task_diff", lambda root: ["HEAD", "MERGE_HEAD"]
    )
    monkeypatch.setattr(
        verify_harness, "git_show", lambda root, ref, rel_path: board("- [R] 내 작업")
    )

    assert verify_harness.check_task_status_promotion(tmp_path) is False


def test_passes_when_no_task_file_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(
        verify_harness, "get_changed_files", lambda root: ["scripts/verify_harness.py"]
    )
    assert verify_harness.check_task_status_promotion(tmp_path) is True
