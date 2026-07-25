"""scripts/check_migration_safety.py 회귀 테스트.

2026-07-23 시드 마이그레이션(5864c6a24a72) 롤백 데이터 손실 사고의
원형 코드가 실제로 검출되는지, 그리고 정상 마이그레이션을 오탐하지 않는지 고정한다.
"""

import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GUARD_PATH = PROJECT_ROOT / "scripts" / "check_migration_safety.py"
SPEC = importlib.util.spec_from_file_location("stockauto_migration_safety", GUARD_PATH)
assert SPEC is not None and SPEC.loader is not None
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


REL_PATH = "backend/alembic/versions/9999abcd_test_migration.py"


def write_migration(root: Path, body: str) -> str:
    path = root / REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "from alembic import op\nimport sqlalchemy as sa\n\n\n" + body,
        encoding="utf-8",
    )
    return REL_PATH


def codes(messages: list[str]) -> set[str]:
    found = set()
    for message in messages:
        for code in ("[R1]", "[R2]", "[R3]", "[R4]", "[R5]"):
            if code in message:
                found.add(code)
    return found


def test_detects_original_incident_pattern(tmp_path):
    """사고 원형: f-string 조립 + 조건 없이 컬럼 전체를 NULL로 미는 롤백."""
    rel = write_migration(
        tmp_path,
        '''DESCRIPTIONS = {"asqs": "설명"}


def upgrade():
    for stype, desc in DESCRIPTIONS.items():
        escaped = desc.replace("'", "''")
        op.execute(
            f"UPDATE strategies SET summary_ko = '{escaped}' "
            f"WHERE strategy_type = '{stype}' AND (summary_ko IS NULL OR summary_ko = '')"
        )


def downgrade():
    for stype in DESCRIPTIONS.keys():
        op.execute(
            f"UPDATE strategies SET summary_ko = NULL WHERE strategy_type = '{stype}'"
        )
''',
    )

    errors, _ = guard.check_file(tmp_path, rel)

    assert "[R1]" in codes(errors), errors
    assert "[R4]" in codes(errors), errors
    # f-string 내부 조각이 별도 SQL로 잡혀 같은 결함이 중복 보고되면 안 된다.
    assert len(errors) == len(set(errors)), errors


def test_accepts_parameterized_narrow_rollback(tmp_path):
    """수정본: 바인드 파라미터 + upgrade가 써넣은 값과 일치하는 행만 되돌림."""
    rel = write_migration(
        tmp_path,
        '''DESCRIPTIONS = {"asqs": "설명"}


def upgrade():
    conn = op.get_bind()
    stmt = sa.text(
        "UPDATE strategies SET summary_ko = :desc "
        "WHERE strategy_type = :stype AND (summary_ko IS NULL OR summary_ko = '')"
    )
    for stype, desc in DESCRIPTIONS.items():
        conn.execute(stmt, {"desc": desc, "stype": stype})


def downgrade():
    conn = op.get_bind()
    stmt = sa.text(
        "UPDATE strategies SET summary_ko = NULL "
        "WHERE strategy_type = :stype AND summary_ko = :desc"
    )
    for stype, desc in DESCRIPTIONS.items():
        conn.execute(stmt, {"desc": desc, "stype": stype})
''',
    )

    errors, warnings = guard.check_file(tmp_path, rel)

    assert errors == []
    assert warnings == []


def test_detects_unconditional_delete(tmp_path):
    rel = write_migration(
        tmp_path,
        '''def upgrade():
    op.execute(sa.text("INSERT INTO strategies (strategy_type) VALUES ('asqs')"))


def downgrade():
    op.execute(sa.text("DELETE FROM strategies"))
''',
    )

    errors, _ = guard.check_file(tmp_path, rel)

    assert "[R2]" in codes(errors), errors


def test_detects_update_without_where(tmp_path):
    rel = write_migration(
        tmp_path,
        '''def upgrade():
    op.execute(sa.text("UPDATE strategies SET tier = 'A' WHERE tier IS NULL"))


def downgrade():
    op.execute(sa.text("UPDATE strategies SET tier = NULL"))
''',
    )

    errors, _ = guard.check_file(tmp_path, rel)

    assert "[R3]" in codes(errors), errors


def test_schema_ddl_downgrade_is_not_flagged(tmp_path):
    """op.drop_column 같은 스키마 롤백은 정상이므로 검출 대상이 아니다."""
    rel = write_migration(
        tmp_path,
        '''def upgrade():
    op.add_column("strategies", sa.Column("summary_ko", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("strategies", "summary_ko")
''',
    )

    errors, warnings = guard.check_file(tmp_path, rel)

    assert errors == []
    assert warnings == []


def test_warns_when_data_migration_has_empty_downgrade(tmp_path):
    rel = write_migration(
        tmp_path,
        '''def upgrade():
    op.execute(sa.text("UPDATE strategies SET tier = 'A' WHERE tier IS NULL"))


def downgrade():
    pass
''',
    )

    errors, warnings = guard.check_file(tmp_path, rel)

    assert errors == []
    assert "[R5]" in codes(warnings), warnings
