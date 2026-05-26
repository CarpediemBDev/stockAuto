import json
import httpx
from app.core.config import settings
from app.core.logging import logger

# 로컬 룰 엔진용 금융 지향 감성 사전
LEXICON_POSITIVE = {
    "surge", "breakout", "upgrade", "profit", "record", "jump", "bullish", "strong", 
    "dividend", "beating", "buy", "success", "launch", "growth", "outperform", 
    "gain", "rise", "positive", "exceed", "earnings beat", "partnership", "alliance"
}

LEXICON_NEGATIVE = {
    "drop", "crash", "downgrade", "loss", "lawsuit", "fall", "investigation", "bearish", 
    "weakness", "layoff", "miss", "concern", "risk", "underperform", "decline", 
    "plunge", "deficit", "fraud", "debt", "shrink", "slump", "negative", "warn"
}

def _analyze_sentiment_locally(ticker: str, news_list: list) -> dict:
    """
    [예비 발전기 / Fallback] 
    제미나이 API 키가 없거나 호출이 실패한 경우 로컬 자연어 규칙 기반으로 즉시 감성 및 요약을 안전 연산합니다.
    """
    logger.info(f"[Local News Analyzer] Fallback activated for {ticker}")
    
    if not news_list:
        return {
            "sentiment": "NEUTRAL",
            "sentiment_score": 50,
            "summary": "최근 등록된 관련 뉴스가 없습니다.",
            "url": ""
        }
        
    score = 50
    pos_count = 0
    neg_count = 0
    
    headlines = []
    first_url = ""
    
    for idx, n in enumerate(news_list[:5]):
        title = n.get("title", "")
        if idx == 0:
            # 첫 번째 뉴스 링크 추출
            first_url = n.get("link", n.get("url", ""))
            
        title_lower = title.lower()
        headlines.append(title)
        
        # 키워드 매칭 계산
        for word in LEXICON_POSITIVE:
            if word in title_lower:
                pos_count += 1
                score += 8
        for word in LEXICON_NEGATIVE:
            if word in title_lower:
                neg_count += 1
                score -= 12
                
    # 점수 가두기 (0 ~ 100)
    score = max(0, min(score, 100))
    
    # 감성 분류
    if score >= 60:
        sentiment = "POSITIVE"
    elif score <= 40:
        sentiment = "NEGATIVE"
    else:
        sentiment = "NEUTRAL"
        
    # 로컬용 한글 요약 생성 (뉴스 제목 기반 룰 변환)
    main_title = headlines[0] if headlines else "관련 소식 감지"
    
    if sentiment == "POSITIVE":
        local_summary = f"📈 [{ticker}] 관련 긍정 소식 감지 (호재 키워드 매칭: '{main_title[:45]}...')"
    elif sentiment == "NEGATIVE":
        local_summary = f"📉 [{ticker}] 관련 경고 소식 감지 (악재 키워드 매칭: '{main_title[:45]}...')"
    else:
        local_summary = f"💬 [{ticker}] 시장 일반 뉴스 감지 ('{main_title[:45]}...')"
        
    return {
        "sentiment": sentiment,
        "sentiment_score": score,
        "summary": local_summary,
        "url": first_url
    }

async def analyze_news_sentiment(ticker: str, news_list: list) -> dict:
    """
    뉴스의 감성을 판독하고 핵심 요약 정보를 반환하는 하이브리드 엔진.
    1. Gemini 1.5 Flash API를 활용하여 정밀 AI 감성 및 한글 요약을 추출합니다.
    2. API 오류 발생 시 즉시 로컬 룰 기반 분석(Fallback)으로 대체 가동됩니다.
    """
    if not news_list:
        return {
            "sentiment": "NEUTRAL",
            "sentiment_score": 50,
            "summary": "최근 관련 뉴스가 존재하지 않습니다.",
            "url": ""
        }
        
    api_key = settings.GEMINI_API_KEY
    first_url = news_list[0].get("link", news_list[0].get("url", ""))
    
    # 1. API Key가 있고 작동하는 경우 Gemini AI 호출 시도
    if api_key and api_key != "your_gemini_api_key_here":
        # 상위 5개 뉴스의 헤드라인 취합
        news_text = "\n".join([f"- {n.get('title')}" for n in news_list[:5]])
        
        prompt = (
            f"Analyze the following financial news headlines for stock ticker '{ticker}'. "
            f"Provide a JSON output ONLY. Do not wrap in markdown or backticks. "
            f"The output must have these exact keys:\n"
            f"- 'sentiment': 'POSITIVE', 'NEGATIVE', or 'NEUTRAL'\n"
            f"- 'score': integer from 0 to 100 (where 100 is highly bullish, 0 is highly bearish, 50 is neutral)\n"
            f"- 'summary': a concise 1-sentence summary translated/written in fluent, natural Korean.\n\n"
            f"News:\n{news_text}"
        )
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json"
            }
        }
        
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(url, json=payload, timeout=8.0)
                if res.status_code == 200:
                    data = res.json()
                    raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    
                    # 마크다운 코드 블록 제거용 방어 로직
                    if raw_text.startswith("```"):
                        lines = raw_text.splitlines()
                        if lines[0].startswith("```"):
                            lines = lines[1:]
                        if lines[-1].startswith("```"):
                            lines = lines[:-1]
                        raw_text = "\n".join(lines).strip()
                        
                    parsed = json.loads(raw_text)
                    
                    logger.info(f"[AI News Analyzer] Successfully analyzed news for {ticker} via Gemini API. Score: {parsed.get('score')}")
                    return {
                        "sentiment": parsed.get("sentiment", "NEUTRAL").upper(),
                        "sentiment_score": int(parsed.get("score", 50)),
                        "summary": parsed.get("summary", "AI 요약을 생성하지 못했습니다."),
                        "url": first_url
                    }
                else:
                    logger.warning(f"[AI News Analyzer] Gemini API failed with status {res.status_code}. Using local fallback.")
        except Exception as e:
            logger.exception(f"[AI News Analyzer] Exception during Gemini API call for {ticker}: {e}")
            
    # 2. 에러가 나거나 API Key가 없는 경우 로컬 룰 엔진 구동
    return _analyze_sentiment_locally(ticker, news_list)
