from app.ai.gemini_client import GeminiClient, GeminiClientError
from app.core.logging import logger
from app.core.system_settings import (
    SETTING_ENABLE_GEMINI_NEWS_ANALYSIS,
    is_system_setting_enabled,
)


LEXICON_POSITIVE = {
    "surge",
    "breakout",
    "upgrade",
    "profit",
    "record",
    "jump",
    "bullish",
    "strong",
    "dividend",
    "beating",
    "buy",
    "success",
    "launch",
    "growth",
    "outperform",
    "gain",
    "rise",
    "positive",
    "exceed",
    "earnings beat",
    "partnership",
    "alliance",
}

LEXICON_NEGATIVE = {
    "drop",
    "crash",
    "downgrade",
    "loss",
    "lawsuit",
    "fall",
    "investigation",
    "bearish",
    "weakness",
    "layoff",
    "miss",
    "concern",
    "risk",
    "underperform",
    "decline",
    "plunge",
    "deficit",
    "fraud",
    "debt",
    "shrink",
    "slump",
    "negative",
    "warn",
}


def _extract_news_title(news_item: dict) -> str:
    if not isinstance(news_item, dict):
        return ""
    content = news_item.get("content")
    if isinstance(content, dict):
        title = str(content.get("title") or "")
        if title:
            return title
    return str(news_item.get("title") or "")


def _extract_news_url(news_item: dict) -> str:
    if not isinstance(news_item, dict):
        return ""
    content = news_item.get("content")
    if isinstance(content, dict):
        click_url = content.get("clickThroughUrl")
        if isinstance(click_url, dict) and click_url.get("url"):
            return str(click_url["url"])
        canonical_url = content.get("canonicalUrl")
        if isinstance(canonical_url, dict) and canonical_url.get("url"):
            return str(canonical_url["url"])
    return str(news_item.get("link") or news_item.get("url") or "")


def _safe_sentiment(value) -> str:
    sentiment = str(value or "NEUTRAL").upper()
    if sentiment not in {"POSITIVE", "NEGATIVE", "NEUTRAL"}:
        return "NEUTRAL"
    return sentiment


def _safe_score(value) -> int:
    try:
        return max(0, min(int(value), 100))
    except (TypeError, ValueError):
        return 50


def _analyze_sentiment_locally(ticker: str, news_list: list) -> dict:
    logger.info("[Local News Analyzer] Fallback activated for %s", ticker)

    if not news_list:
        return {
            "sentiment": "NEUTRAL",
            "sentiment_score": 50,
            "summary": "최근 등록된 관련 뉴스가 없습니다.",
            "url": "",
            "source": "local",
        }

    score = 50
    headlines = []
    first_url = ""

    for idx, news_item in enumerate(news_list[:5]):
        title = _extract_news_title(news_item)
        if idx == 0:
            first_url = _extract_news_url(news_item)

        title_lower = title.lower()
        headlines.append(title)

        for word in LEXICON_POSITIVE:
            if word in title_lower:
                score += 8
        for word in LEXICON_NEGATIVE:
            if word in title_lower:
                score -= 12

    score = max(0, min(score, 100))

    if score >= 60:
        sentiment = "POSITIVE"
    elif score <= 40:
        sentiment = "NEGATIVE"
    else:
        sentiment = "NEUTRAL"

    main_title = headlines[0] if headlines else "관련 소식 감지"
    if sentiment == "POSITIVE":
        local_summary = f"[{ticker}] 긍정 뉴스 감지: '{main_title[:45]}...'"
    elif sentiment == "NEGATIVE":
        local_summary = f"[{ticker}] 경고 뉴스 감지: '{main_title[:45]}...'"
    else:
        local_summary = f"[{ticker}] 일반 뉴스 감지: '{main_title[:45]}...'"

    return {
        "sentiment": sentiment,
        "sentiment_score": score,
        "summary": local_summary,
        "url": first_url,
        "source": "local",
    }


async def analyze_news_sentiment(ticker: str, news_list: list, force_local: bool = False) -> dict:
    """
    Analyze scanner news sentiment.

    Gemini is a runtime feature flag, disabled by default through system_settings.
    When it is disabled, unconfigured, or fails, local lexicon fallback is used.
    If force_local is True, Gemini is bypassed to save API quota.
    """
    if not news_list:
        return {
            "sentiment": "NEUTRAL",
            "sentiment_score": 50,
            "summary": "최근 관련 뉴스가 존재하지 않습니다.",
            "url": "",
            "source": "none",
        }

    first_url = _extract_news_url(news_list[0])

    if not force_local and is_system_setting_enabled(SETTING_ENABLE_GEMINI_NEWS_ANALYSIS):
        news_text = "\n".join(
            f"- {title}"
            for title in (_extract_news_title(item) for item in news_list[:5])
            if title
        )
        prompt = (
            f"Analyze the following financial news headlines for stock ticker '{ticker}'. "
            "Provide a JSON output ONLY. Do not wrap in markdown or backticks. "
            "The output must have these exact keys:\n"
            "- 'sentiment': 'POSITIVE', 'NEGATIVE', or 'NEUTRAL'\n"
            "- 'score': integer from 0 to 100 (where 100 is highly bullish, 0 is highly bearish, 50 is neutral)\n"
            "- 'summary': a concise 1-sentence summary translated/written in fluent, natural Korean.\n\n"
            f"News:\n{news_text}"
        )

        try:
            parsed = await GeminiClient().generate_json(prompt)
            score = _safe_score(parsed.get("score", 50))
            logger.info(
                "[AI News Analyzer] Successfully analyzed news for %s via Gemini API. Score: %s",
                ticker,
                score,
            )
            return {
                "sentiment": _safe_sentiment(parsed.get("sentiment")),
                "sentiment_score": score,
                "summary": parsed.get("summary", "AI 요약을 생성하지 못했습니다."),
                "url": first_url,
                "source": "gemini",
            }
        except GeminiClientError as exc:
            logger.exception(
                "[AI News Analyzer] Exception during Gemini API call for %s: %s",
                ticker,
                exc,
            )
    elif force_local:
        logger.info(
            "[AI News Analyzer] Gemini skipped (quota throttle) for %s. Local fallback.",
            ticker,
        )
    else:
        logger.info(
            "[AI News Analyzer] Gemini disabled (setting off) for %s. Local fallback.",
            ticker,
        )

    return _analyze_sentiment_locally(ticker, news_list)
