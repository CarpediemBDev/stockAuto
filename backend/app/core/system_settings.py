import json
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.core.database import SessionLocal
from app.core.logging import logger
from app.core.models import SystemSetting, utc_now_aware


@dataclass(frozen=True)
class SystemSettingSpec:
    key: str
    default: Any
    value_type: str
    category: str
    description: str
    is_runtime: bool = True
    is_public: bool = False


SETTING_ENABLE_GEMINI_NEWS_ANALYSIS = "enable_gemini_news_analysis"

SYSTEM_SETTING_SPECS: dict[str, SystemSettingSpec] = {
    SETTING_ENABLE_GEMINI_NEWS_ANALYSIS: SystemSettingSpec(
        key=SETTING_ENABLE_GEMINI_NEWS_ANALYSIS,
        default=False,
        value_type="bool",
        category="ai",
        description="Enable Gemini-backed AI analysis for scanner news headlines.",
        is_runtime=True,
        is_public=False,
    ),
}

_CACHE_TTL_SECONDS = 30.0
_cache: dict[str, tuple[float, Any]] = {}


class SystemSettingError(ValueError):
    pass


def clear_system_settings_cache() -> None:
    _cache.clear()


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    raise SystemSettingError(f"Invalid bool system setting value: {value!r}")


def _serialize_value(value: Any, value_type: str) -> str:
    if value_type == "bool":
        return "true" if _coerce_bool(value) else "false"
    if value_type == "int":
        return str(int(value))
    if value_type == "float":
        return str(float(value))
    if value_type == "json":
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value_type == "string":
        return str(value)
    raise SystemSettingError(f"Unsupported system setting type: {value_type}")


def _parse_value(raw_value: str, value_type: str) -> Any:
    if value_type == "bool":
        return _coerce_bool(raw_value)
    if value_type == "int":
        return int(raw_value)
    if value_type == "float":
        return float(raw_value)
    if value_type == "json":
        return json.loads(raw_value)
    if value_type == "string":
        return str(raw_value)
    raise SystemSettingError(f"Unsupported system setting type: {value_type}")


def parse_system_setting_value(raw_value: str, value_type: str) -> Any:
    return _parse_value(raw_value, value_type)


def serialize_system_setting_value(value: Any, value_type: str) -> str:
    return _serialize_value(value, value_type)


def upsert_system_setting_in_session(
    db,
    key: str,
    value: Any,
    updated_by: int | None = None,
) -> SystemSetting:
    spec = SYSTEM_SETTING_SPECS.get(key)
    if spec is None:
        raise SystemSettingError(f"Unknown system setting key: {key}")

    serialized = _serialize_value(value, spec.value_type)
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if row is None:
        row = SystemSetting(
            key=key,
            value=serialized,
            value_type=spec.value_type,
            category=spec.category,
            description=spec.description,
            is_runtime=spec.is_runtime,
            is_public=spec.is_public,
            updated_by=updated_by,
        )
        db.add(row)
    else:
        row.value = serialized
        row.value_type = spec.value_type
        row.category = spec.category
        row.description = spec.description
        row.is_runtime = spec.is_runtime
        row.is_public = spec.is_public
        row.updated_by = updated_by
        row.updated_at = utc_now_aware()
    clear_system_settings_cache()
    return row


def get_system_setting(key: str) -> Any:
    spec = SYSTEM_SETTING_SPECS.get(key)
    if spec is None:
        raise SystemSettingError(f"Unknown system setting key: {key}")

    now = time.time()
    cached = _cache.get(key)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    value = spec.default
    db = SessionLocal()
    try:
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if row is not None:
            value = _parse_value(row.value, row.value_type)
    except (SQLAlchemyError, SystemSettingError) as exc:
        logger.warning(
            "[SystemSettings] Falling back to default for %s after lookup failure: %s",
            key,
            exc,
        )
        value = spec.default
    finally:
        db.close()

    _cache[key] = (now, value)
    return value


def is_system_setting_enabled(key: str) -> bool:
    return bool(get_system_setting(key))


def upsert_system_setting(key: str, value: Any, updated_by: int | None = None) -> SystemSetting:
    db = SessionLocal()
    try:
        row = upsert_system_setting_in_session(db, key, value, updated_by)
        db.commit()
        db.refresh(row)
        db.expunge(row)
        return row
    finally:
        db.close()
