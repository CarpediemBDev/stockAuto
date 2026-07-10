import pytest

import app.scanner.news_analyzer as news_analyzer


@pytest.mark.asyncio
async def test_news_analyzer_uses_local_fallback_when_gemini_disabled(monkeypatch):
    monkeypatch.setattr(news_analyzer, "is_system_setting_enabled", lambda _key: False)

    class FailingGeminiClient:
        async def generate_json(self, prompt):
            raise AssertionError("Gemini must not be called when disabled")

    monkeypatch.setattr(news_analyzer, "GeminiClient", FailingGeminiClient)

    result = await news_analyzer.analyze_news_sentiment(
        "NVDA",
        [{"title": "NVDA shares surge after AI partnership", "link": "https://example.test/news"}],
    )

    assert result["sentiment"] == "POSITIVE"
    assert result["sentiment_score"] > 50
    assert result["url"] == "https://example.test/news"


@pytest.mark.asyncio
async def test_news_analyzer_uses_common_gemini_adapter_when_enabled(monkeypatch):
    monkeypatch.setattr(news_analyzer, "is_system_setting_enabled", lambda _key: True)
    captured = {}

    class FakeGeminiClient:
        async def generate_json(self, prompt):
            captured["prompt"] = prompt
            return {
                "sentiment": "positive",
                "score": 120,
                "summary": "엔비디아 관련 호재가 감지되었습니다.",
            }

    monkeypatch.setattr(news_analyzer, "GeminiClient", FakeGeminiClient)

    result = await news_analyzer.analyze_news_sentiment(
        "NVDA",
        [
            {
                "content": {
                    "title": "NVDA announces major AI contract",
                    "canonicalUrl": {"url": "https://example.test/content-url"},
                }
            }
        ],
    )

    assert "NVDA announces major AI contract" in captured["prompt"]
    assert result == {
        "sentiment": "POSITIVE",
        "sentiment_score": 100,
        "summary": "엔비디아 관련 호재가 감지되었습니다.",
        "url": "https://example.test/content-url",
        "source": "gemini",
    }
