# -*- coding: utf-8 -*-
"""Alembic 마이그레이션 안전성 정적 검사기.

2026-07-23 시드 마이그레이션(5864c6a24a72) 사고 재발 방지용 가드다.
사고 원형:

    def downgrade():
        for stype in DESCRIPTIONS.keys():
            op.execute(
                f"UPDATE strategies SET summary_ko = NULL "
                f"WHERE strategy_type = '{stype}'"
            )

upgrade()는 '비어 있던 행만' 채웠는데 downgrade()는 해당 전략 타입의 모든 행을
NULL로 밀어버려, 원래 있던 설명과 사람이 손으로 고친 문구까지 영구 소실시킨다.
게다가 SQL을 f-string으로 조립해 따옴표 이스케이프를 수동 처리하고 있었다.

이 검사기는 마이그레이션을 '실행하지 않고' 파이썬 AST만 읽어 판정하므로
DB가 없는 CI에서도 동일하게 동작한다.

검사 대상은 이번 변경분에 포함된 backend/alembic/versions/*.py 뿐이다.
기존 마이그레이션은 수정하지 않는 한 검사하지 않으므로 과거 파일 때문에
영구 FAIL이 나지 않는다. (--all 로 전수 감사 가능)
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    # verify_harness는 자식 프로세스 stdout을 utf-8로 디코딩한다.
    # Windows 기본 로케일(cp949)로 나가면 한글이 깨지므로 강제 고정한다.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


MIGRATION_DIR = "backend/alembic/versions/"

# SQL 문자열 판별: 데이터 DML 키워드가 들어간 문자열만 SQL로 취급한다.
SQL_HINT_RE = re.compile(r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b", re.IGNORECASE)
DELETE_RE = re.compile(r"\bDELETE\s+FROM\s+(\S+)", re.IGNORECASE)
UPDATE_RE = re.compile(r"\bUPDATE\s+(\S+)\s+SET\b", re.IGNORECASE)
WHERE_RE = re.compile(r"\bWHERE\b(.*)", re.IGNORECASE | re.DOTALL)
# "SET a = NULL, b = :x" 에서 NULL로 지워지는 컬럼만 뽑는다.
SET_NULL_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*NULL", re.IGNORECASE)

# 동적 SQL 조립 검사에서 인자를 들여다볼 호출 이름.
SQL_SINK_NAMES = {"execute", "text", "executemany"}

FSTRING_PLACEHOLDER = "<expr>"


def load_harness_helpers(root: Path):
    """verify_harness의 변경파일 탐지 로직을 재사용한다(SSOT 중복 구현 금지)."""
    harness_path = root / "scripts" / "verify_harness.py"
    spec = importlib.util.spec_from_file_location(
        "stockauto_verify_harness_for_migration_guard", harness_path
    )
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def changed_migration_files(root: Path) -> list[str]:
    helpers = load_harness_helpers(root)
    if helpers is None:
        return []
    changed = helpers.get_changed_files(root)
    return [
        path
        for path in changed
        if path.startswith(MIGRATION_DIR)
        and path.endswith(".py")
        and not Path(path).name.startswith("__")
    ]


def all_migration_files(root: Path) -> list[str]:
    versions_dir = root / "backend" / "alembic" / "versions"
    if not versions_dir.is_dir():
        return []
    return sorted(
        f"{MIGRATION_DIR}{path.name}"
        for path in versions_dir.glob("*.py")
        if not path.name.startswith("__")
    )


def sql_from_node(node: ast.AST) -> str | None:
    """AST 노드에서 SQL 문자열을 최대한 복원한다. SQL이 아니면 None."""
    text: str | None = None

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        text = node.value
    elif isinstance(node, ast.JoinedStr):
        # f-string은 치환부를 자리표시자로 바꿔 WHERE 절 구조만 남긴다.
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                parts.append(FSTRING_PLACEHOLDER)
        text = "".join(parts)
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = sql_from_node(node.left)
        right = sql_from_node(node.right)
        if left is None and right is None:
            return None
        text = f"{left or FSTRING_PLACEHOLDER}{right or FSTRING_PLACEHOLDER}"

    if text is None or not SQL_HINT_RE.search(text):
        return None
    return text


def iter_sql_strings(func: ast.FunctionDef):
    """함수 본문에 등장하는 SQL 문자열을 (라인, SQL) 로 훑는다.

    한 번 SQL로 인정한 노드의 내부는 다시 훑지 않는다. f-string은 자기 자신과
    내부 조각(잘린 SQL)이 각각 잡혀 같은 결함이 중복 보고되기 때문이다.
    """
    queue = list(ast.iter_child_nodes(func))
    while queue:
        node = queue.pop(0)
        sql = sql_from_node(node)
        if sql is not None:
            yield getattr(node, "lineno", func.lineno), sql
            continue
        queue.extend(ast.iter_child_nodes(node))


def call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def is_dynamic_sql(node: ast.AST) -> bool:
    """f-string / % / .format() 으로 조립된 SQL인지 판정."""
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(v, ast.FormattedValue) for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        return sql_from_node(node.left) is not None
    if isinstance(node, ast.Call) and call_name(node) == "format":
        target = node.func.value if isinstance(node.func, ast.Attribute) else None
        return target is not None and sql_from_node(target) is not None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        # "SELECT ..." + variable 형태의 조립
        if sql_from_node(node) is None:
            return False
        for side in (node.left, node.right):
            if not isinstance(side, (ast.Constant, ast.JoinedStr, ast.BinOp)):
                return True
        return is_dynamic_sql(node.left) or is_dynamic_sql(node.right)
    return False


def check_dynamic_sql(tree: ast.AST, rel_path: str) -> list[str]:
    """R1: SQL을 문자열로 조립하는 마이그레이션 금지."""
    errors: list[str] = []
    seen: set[int] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if call_name(node) not in SQL_SINK_NAMES:
            continue
        for arg in node.args:
            if sql_from_node(arg) is None:
                continue
            if not is_dynamic_sql(arg):
                continue
            lineno = getattr(arg, "lineno", node.lineno)
            if lineno in seen:
                continue
            seen.add(lineno)
            errors.append(
                f"{rel_path}:{lineno} [R1] SQL을 f-string/%/.format() 으로 조립했습니다. "
                "sa.text()와 바인드 파라미터(:name)를 사용하세요."
            )
    return errors


def where_clause(sql: str) -> str | None:
    match = WHERE_RE.search(sql)
    if match is None:
        return None
    return match.group(1)


def check_downgrade_dml(func: ast.FunctionDef, rel_path: str) -> list[str]:
    """R2~R4: downgrade()의 데이터 파괴 패턴 검출.

    op.drop_column() 같은 스키마 DDL은 정상적인 롤백이므로 대상이 아니다.
    이 함수는 문자열 SQL만 본다.
    """
    errors: list[str] = []

    for lineno, sql in iter_sql_strings(func):
        where = where_clause(sql)

        delete_match = DELETE_RE.search(sql)
        if delete_match and where is None:
            errors.append(
                f"{rel_path}:{lineno} [R2] downgrade()가 WHERE 없이 "
                f"DELETE FROM {delete_match.group(1)} 을 수행합니다. 테이블 전체가 삭제됩니다."
            )
            continue

        update_match = UPDATE_RE.search(sql)
        if not update_match:
            continue

        table = update_match.group(1)
        if where is None:
            errors.append(
                f"{rel_path}:{lineno} [R3] downgrade()가 WHERE 없이 "
                f"UPDATE {table} 을 수행합니다. 해당 테이블 전체 행이 덮어써집니다."
            )
            continue

        # R4: 되돌리려는 컬럼을 NULL로 미는데, WHERE가 그 컬럼값을 확인하지 않는 경우.
        # upgrade()가 채운 값과 무관하게 기존 데이터까지 지워지는 비가역 롤백이다.
        set_part = sql[update_match.end():]
        if where is not None:
            set_part = set_part[: set_part.lower().rfind("where")]
        nulled_columns = {name.lower() for name in SET_NULL_RE.findall(set_part)}
        where_lower = where.lower()
        for column in sorted(nulled_columns):
            if re.search(rf"\b{re.escape(column)}\b", where_lower):
                continue
            errors.append(
                f"{rel_path}:{lineno} [R4] downgrade()가 {table}.{column} 을 NULL로 되돌리면서 "
                f"WHERE 절에서 {column} 값을 확인하지 않습니다. "
                "upgrade()가 써넣은 값과 일치하는 행만 되돌리도록 조건을 좁히세요 "
                f"(예: WHERE ... AND {column} = :expected)."
            )

    return errors


def has_data_dml(func: ast.FunctionDef) -> bool:
    return any(True for _ in iter_sql_strings(func))


def is_effectively_empty(func: ast.FunctionDef) -> bool:
    body = [
        stmt
        for stmt in func.body
        if not (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        )
    ]
    return all(isinstance(stmt, ast.Pass) for stmt in body)


def check_file(root: Path, rel_path: str) -> tuple[list[str], list[str]]:
    absolute = root / rel_path
    if not absolute.exists():
        return [], []

    source = absolute.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(absolute))
    except SyntaxError as exc:
        return [f"{rel_path}: 구문 오류로 검사 불가 ({exc})"], []

    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }

    errors = check_dynamic_sql(tree, rel_path)
    warnings: list[str] = []

    downgrade = functions.get("downgrade")
    if downgrade is not None:
        errors.extend(check_downgrade_dml(downgrade, rel_path))

    upgrade = functions.get("upgrade")
    if (
        upgrade is not None
        and has_data_dml(upgrade)
        and (downgrade is None or is_effectively_empty(downgrade))
    ):
        warnings.append(
            f"{rel_path}: [R5] upgrade()는 데이터를 변경하는데 downgrade()가 비어 있습니다. "
            "롤백 불가 마이그레이션입니다."
        )

    return errors, warnings


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if a != "--all"]
    scan_all = "--all" in argv[1:]
    root = Path(args[0]) if args else Path(__file__).resolve().parents[1]

    targets = all_migration_files(root) if scan_all else changed_migration_files(root)

    if not targets:
        print("  [OK] Migration safety: 검사 대상 마이그레이션 변경 없음.")
        return 0

    all_errors: list[str] = []
    all_warnings: list[str] = []
    for rel_path in targets:
        errors, warnings = check_file(root, rel_path)
        all_errors.extend(errors)
        all_warnings.extend(warnings)

    for warning in all_warnings:
        print(f"  [WARN] {warning}")

    if all_errors:
        print(f"  [FAIL] Migration safety: {len(all_errors)}건의 비가역/불안전 패턴이 검출되었습니다.")
        for error in all_errors:
            print(f"    - {error}")
        return 1

    print(f"  [OK] Migration safety: {len(targets)}개 마이그레이션 검사 통과.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
