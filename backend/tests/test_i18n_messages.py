"""다국어 알림 메시지(I18n) 회귀 테스트.

핵심 불변식:
1. 키를 못 찾아도 사용자에게 날 키 문자열('ui.order_resolved')이 전달되지 않는다
   — default가 있으면 default, 없으면 ko로 강등한다. 실제로 텔레그램에 키가
   그대로 노출되던 결함의 재발 방지가 이 파일의 존재 이유다.
2. default는 이름 있는 매개변수이며 포맷 인자로 오염되지 않는다.
3. 알림 언어는 UserSettings.language에서 결정되고, 조회가 실패해도 'ko'로 폴백한다.
4. ko/en 딕셔너리는 같은 키 집합을 가지며 플레이스홀더도 일치한다.
"""

import json
import pathlib
import re

import pytest

from app.core.i18n import I18n, resolve_user_language

LOCALES_DIR = pathlib.Path(__file__).resolve().parents[2] / "locales"


def _load(lang: str) -> dict:
    return json.loads((LOCALES_DIR / f"{lang}.json").read_text(encoding="utf-8"))


def _flatten(d: dict, prefix: str = "") -> dict:
    flat = {}
    for key, value in d.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten(value, path))
        else:
            flat[path] = value
    return flat


class TestMissingKeyNeverLeaks:
    def test_missing_key_with_default_returns_default(self):
        result = I18n.get_msg("ko", "ui.__does_not_exist__", default="대체 문구")
        assert result == "대체 문구"

    def test_missing_key_without_default_degrades_to_key(self):
        # default가 없으면 키로 강등되지만, 이 경우 WARNING 로그가 남아 탐지 가능해야 한다.
        result = I18n.get_msg("ko", "ui.__does_not_exist__")
        assert result == "ui.__does_not_exist__"

    def test_order_resolved_key_actually_exists(self):
        # 결함 재발 방지: 이 키가 비면 텔레그램 본문에 'ui.order_resolved'가 노출됐었다.
        result = I18n.get_msg("ko", "ui.order_resolved", default="fallback")
        assert result != "ui.order_resolved"
        assert result != "fallback"
        assert "봇" in result

    def test_default_is_not_consumed_as_format_arg(self):
        # default가 **kwargs로 새면 포맷 인자로 오해된다 — 이름 있는 매개변수여야 한다.
        result = I18n.get_msg("ko", "telegram.orphan_order_recovered",
                              default="쓰이면 안 됨",
                              side="BUY", ticker="AAPL",
                              broker_order_no="123", status="FILLED")
        assert "쓰이면 안 됨" not in result
        assert "AAPL" in result


class TestLanguageFallback:
    def test_unknown_language_falls_back_to_ko(self):
        ko = I18n.get_msg("ko", "ui.order_resolved")
        assert I18n.get_msg("fr", "ui.order_resolved") == ko

    def test_empty_language_falls_back_to_ko(self):
        ko = I18n.get_msg("ko", "ui.order_resolved")
        assert I18n.get_msg("", "ui.order_resolved") == ko
        assert I18n.get_msg(None, "ui.order_resolved") == ko

    def test_english_returns_english(self):
        result = I18n.get_msg("en", "ui.order_resolved")
        assert result != I18n.get_msg("ko", "ui.order_resolved")
        assert "Bot status" in result


class TestResolveUserLanguage:
    def test_returns_ko_when_lookup_raises(self):
        class BrokenDB:
            def query(self, *a, **k):
                raise RuntimeError("db is down")

        # 알림 자체는 나가야 하므로 조회 실패는 항상 ko로 폴백한다.
        assert resolve_user_language(BrokenDB(), 1) == "ko"

    def test_returns_ko_when_settings_missing(self):
        class EmptyDB:
            def query(self, *a, **k):
                return self

            def filter(self, *a, **k):
                return self

            def scalar(self):
                return None

        assert resolve_user_language(EmptyDB(), 1) == "ko"

    def test_returns_stored_language(self):
        class EnDB:
            def query(self, *a, **k):
                return self

            def filter(self, *a, **k):
                return self

            def scalar(self):
                return "en"

        assert resolve_user_language(EnDB(), 1) == "en"


class TestDictionaryParity:
    def test_ko_and_en_have_identical_key_sets(self):
        ko_keys = set(_flatten(_load("ko")))
        en_keys = set(_flatten(_load("en")))
        assert ko_keys == en_keys, (
            f"ko 전용: {sorted(ko_keys - en_keys)} / en 전용: {sorted(en_keys - ko_keys)}"
        )

    def test_placeholders_match_across_languages(self):
        ko = _flatten(_load("ko"))
        en = _flatten(_load("en"))
        placeholder = re.compile(r"\{(\w+)")
        for key, ko_text in ko.items():
            if not isinstance(ko_text, str):
                continue
            # 플레이스홀더가 어긋나면 한쪽 언어에서만 KeyError로 포맷이 깨진다.
            assert set(placeholder.findall(ko_text)) == set(placeholder.findall(en[key])), key

    def test_no_empty_namespace_left_behind(self):
        # 빈 네임스페이스는 '연결됐다고 착각하지만 키가 없는' 상태를 만든다.
        # exception 네임스페이스가 정확히 이 상태로 방치되어 있었고, 참조하는 코드가
        # 하나도 없어 제거했다. 예외 메시지 다국어화를 실제로 구현할 때 키와 함께 추가할 것.
        for lang in ("ko", "en"):
            for namespace, body in _load(lang).items():
                assert body, f"{lang}.json의 '{namespace}' 네임스페이스가 비어 있음"


class TestFrontendConsumedKeysExist:
    """프론트가 useTranslations로 요청하는 키가 딕셔너리에 실재하는지 검증한다.

    소비자 코드만 병합되고 딕셔너리가 빠져 화면에 키 경로가 노출되던 상태를 막는다.
    """

    FRONTEND = pathlib.Path(__file__).resolve().parents[2] / "frontend"

    def _consumed_keys(self) -> set[str]:
        namespace_re = re.compile(r"const\s+(\w+)\s*=\s*useTranslations\(\s*['\"]([^'\"]+)['\"]\s*\)")
        consumed = set()
        for path in self.FRONTEND.rglob("*.tsx"):
            if "node_modules" in path.parts or ".next" in str(path):
                continue
            source = path.read_text(encoding="utf-8", errors="ignore")
            for var, namespace in namespace_re.findall(source):
                for key in re.findall(rf"\b{var}\(\s*['\"]([^'\"]+)['\"]", source):
                    consumed.add(f"{namespace}.{key}")
        return consumed

    def test_every_consumed_key_is_defined(self):
        consumed = self._consumed_keys()
        assert consumed, "useTranslations 소비 키를 하나도 찾지 못했다 — 추출 정규식 점검 필요"
        defined = set(_flatten(_load("ko")))
        missing = sorted(consumed - defined)
        assert not missing, f"프론트가 쓰는데 ko.json에 없는 키: {missing}"

    def _namespace_of(self, source: str) -> str | None:
        match = re.search(r"useTranslations\(\s*['\"]([^'\"]+)['\"]\s*\)", source)
        return match.group(1) if match else None

    def test_dynamic_label_keys_are_defined(self):
        """t(item.labelKey)처럼 동적으로 부르는 키는 위 정규식이 잡지 못한다.

        모듈 상수에 담긴 labelKey를 파일별로 긁어, 그 파일이 선언한 네임스페이스와
        합쳐 딕셔너리와 대조한다. 라벨이 키 경로 그대로 화면에 노출되는 사고를 막는
        최소 방어선이며, 현재 NavBar(nav)와 ScannerTabs(scanner)가 이 패턴을 쓴다.
        """
        found = 0
        for path in self.FRONTEND.rglob("*.tsx"):
            if "node_modules" in path.parts or ".next" in str(path):
                continue
            source = path.read_text(encoding="utf-8", errors="ignore")
            label_keys = re.findall(r"labelKey:\s*['\"]([^'\"]+)['\"]", source)
            if not label_keys:
                continue
            namespace = self._namespace_of(source)
            assert namespace, f"{path.name}: labelKey는 있는데 useTranslations 네임스페이스가 없다"
            for lang in ("ko", "en"):
                defined = set(_flatten(_load(lang)))
                for key in label_keys:
                    assert f"{namespace}.{key}" in defined, f"{lang}.json에 {namespace}.{key} 없음"
                    found += 1
        assert found, "labelKey 패턴을 하나도 찾지 못했다 — 구조가 바뀌었는지 확인 필요"

    def test_after_hours_signal_labels_are_defined(self):
        """AfterHoursScanner는 SIGNAL_LABEL 상수를 거쳐 t()를 템플릿 리터럴로 부른다.

        상수 값이 곧 번역 키 접미사이므로, 딕셔너리에 실재하지 않으면 배지에
        'label_strong' 같은 내부 식별자가 그대로 찍힌다.
        """
        source = (self.FRONTEND / "components" / "AfterHoursScanner.tsx").read_text(encoding="utf-8")
        block = re.search(r"const SIGNAL_LABEL = \{(.*?)\}", source, re.S)
        assert block, "SIGNAL_LABEL 상수를 찾지 못했다 — 구조가 바뀌었는지 확인 필요"
        suffixes = re.findall(r":\s*['\"]([^'\"]+)['\"]", block.group(1))
        assert suffixes, "SIGNAL_LABEL 값이 비어 있다"
        for lang in ("ko", "en"):
            defined = set(_flatten(_load(lang)))
            for suffix in suffixes:
                assert f"scanner.after_hours.{suffix}" in defined, \
                    f"{lang}.json에 scanner.after_hours.{suffix} 없음"


class TestDiscoveryNotificationLocalized:
    @pytest.mark.parametrize("lang,marker", [("ko", "보류"), ("en", "Deferred")])
    def test_ambiguous_notification_has_both_languages(self, lang, marker):
        result = I18n.get_msg(lang, "telegram.order_recovery_ambiguous",
                              side="BUY", ticker="TSLA", candidate_count=3)
        assert marker in result
        assert "TSLA" in result
        assert "3" in result


class TestNoHardcodedKoreanInFrontend:
    """프론트 .ts/.tsx의 주석 밖 한글 리터럴을 스캔해 하드코딩 재발을 차단한다.

    TestFrontendConsumedKeysExist는 useTranslations로 '소비된 키'만 검증하므로,
    t()를 아예 쓰지 않고 한글을 그대로 박은 컴포넌트(UserManagement가 스테이지 8을
    빠져나간 사각지대)는 잡지 못한다. 이 테스트는 그 구멍을 메운다.

    의도적으로 한글을 남긴 곳은 ALLOWLIST로 명시 관리한다. 값이 None이면 파일 전체
    허용, set이면 그 부분문자열을 포함한 줄만 허용한다. 향후 해당 문구를 실제로
    다국어화하면 ALLOWLIST에서 제거해야 새 하드코딩을 가리지 않는다.
    """

    FRONTEND = pathlib.Path(__file__).resolve().parents[2] / "frontend"
    HANGUL = re.compile(r"[가-힣]")
    BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
    LINE_COMMENT = re.compile(r"(?<!:)//.*$")  # ':' 뒤 //는 URL이라 보존

    # 의도적 잔존분(감사·설계 결정). None=파일 전체 허용, set=부분문자열 허용.
    ALLOWLIST: dict[str, set[str] | None] = {
        # 루트 레이아웃을 대체해 NextIntlClientProvider 밖에서 렌더 → 인라인 ko/en 딕셔너리(설계상 불가피)
        "app/global-error.tsx": None,
        # SEO 메타데이터(정적) — 낮은 우선순위로 보류
        "app/layout.tsx": None,
        # 순수 모듈 함수라 useTranslations 불가 → 호출부 리팩터 필요(보류)
        "lib/utils.ts": {"알 수 없는 오류가 발생했습니다."},
        "lib/api.ts": {"인증 갱신 응답 형식이 올바르지 않습니다."},
        # 언어 전환 확인(대상 언어로 표기하는 이중언어) + 언어 셀렉터 자기명명
        "components/NavBar.tsx": {"한국어로 변경되었습니다.", "한국어 (KR)"},
    }

    SKIP_DIRS = {"node_modules", ".next", "e2e", "coverage", "test-results", "playwright-report"}
    SKIP_FILES = {"playwright.config.ts", "next.config.ts", "i18n.ts"}

    def _violations(self) -> list[str]:
        hits: list[str] = []
        for path in self.FRONTEND.rglob("*.ts*"):
            if path.suffix not in (".ts", ".tsx"):
                continue
            if set(path.parts) & self.SKIP_DIRS:
                continue
            if path.name in self.SKIP_FILES or path.name.endswith((".spec.ts", ".test.ts", ".test.tsx")):
                continue
            rel = path.relative_to(self.FRONTEND).as_posix()
            allowed = self.ALLOWLIST.get(rel, "__MISSING__")
            if allowed is None:
                continue  # 파일 전체 허용
            source = self.BLOCK_COMMENT.sub("", path.read_text(encoding="utf-8", errors="ignore"))
            for i, raw in enumerate(source.splitlines(), 1):
                line = self.LINE_COMMENT.sub("", raw)
                if not self.HANGUL.search(line):
                    continue
                if allowed != "__MISSING__" and any(sub in line for sub in allowed):
                    continue
                hits.append(f"{rel}:{i}: {line.strip()[:100]}")
        return hits

    def test_no_unallowlisted_hardcoded_korean(self):
        violations = self._violations()
        assert not violations, (
            "t() 없이 하드코딩된 한글 문구를 발견했습니다. 다국어화하거나, 의도적이라면 "
            "TestNoHardcodedKoreanInFrontend.ALLOWLIST에 사유와 함께 등록하세요:\n"
            + "\n".join(violations)
        )
