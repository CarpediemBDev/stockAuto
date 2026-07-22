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
SETTING_ENABLE_SCANNER_RELAY = "enable_scanner_relay"

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
    # 릴레이는 이미 가동 중인 기능이므로 기본값은 ON이다. 이 스위치는 신규 기능의
    # opt-in이 아니라 '오작동 시 재배포 없이 즉시 끄는' 킬 스위치이며, DB 조회
    # 실패 시 get_system_setting이 default로 폴백하므로 일시적 DB 장애가 매매
    # 대상을 조용히 바꾸지 않는다.
    SETTING_ENABLE_SCANNER_RELAY: SystemSettingSpec(
        key=SETTING_ENABLE_SCANNER_RELAY,
        default=True,
        value_type="bool",
        category="scanner",
        description="Enable the scanner relay that feeds after-hours and swing-prediction candidates into the intraday scan universe.",
        is_runtime=True,
        is_public=False,
    ),
}

_CACHE_TTL_SECONDS = 30.0
_CACHE_VERSION_CHECK_SECONDS = 1.0
_MISSING_ROW_VERSION = "__missing__"
_ERROR_ROW_VERSION = "__error__"
_cache: dict[str, tuple[float, float, Any, str]] = {}


class SystemSettingError(ValueError):
    pass


def clear_system_settings_cache() -> None:
    _cache.clear()


def _row_version(row: SystemSetting | None) -> str:
    if row is None:
        return _MISSING_ROW_VERSION
    version = row.updated_at or row.created_at
    if version is None:
        return ""
    if hasattr(version, "isoformat"):
        return version.isoformat()
    return str(version)


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
    if cached:
        loaded_at, checked_at, cached_value, _cached_version = cached
        if (
            now - loaded_at < _CACHE_TTL_SECONDS
            and now - checked_at < _CACHE_VERSION_CHECK_SECONDS
        ):
            return cached_value

    value = spec.default
    version = _MISSING_ROW_VERSION
    db = SessionLocal()
    try:
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        version = _row_version(row)
        if cached:
            loaded_at, _checked_at, cached_value, cached_version = cached
            if (
                cached_version == version
                and now - loaded_at < _CACHE_TTL_SECONDS
            ):
                _cache[key] = (loaded_at, now, cached_value, cached_version)
                return cached_value
        if row is not None:
            value = _parse_value(row.value, row.value_type)
    except (SQLAlchemyError, SystemSettingError) as exc:
        logger.warning(
            "[SystemSettings] Falling back to default for %s after lookup failure: %s",
            key,
            exc,
        )
        value = spec.default
        version = _ERROR_ROW_VERSION
    finally:
        db.close()

    _cache[key] = (now, now, value, version)
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
