import asyncio
import pandas as pd
import numpy as np
from app.scanner.data_provider import fetch_ohlcv
from app.scanner.indicators import (
    calculate_volume_dryup,
    calculate_bb_squeeze,
    calculate_obv_divergence,
    detect_vcp_pattern,
    calculate_ema
)
from app.core.logging import logger

async def analyze_swing_setup(ticker: str) -> dict:
    """
    단일 종목의 120일 누적 일봉 데이터를 분석하여
    '세력이 움직이기 직전(거래량 극감, 변동성 대수축, OBV 매집)' 상태를 0~100점 만점으로 계량화합니다.
    """
    try:
        # 1. 누적 일봉 데이터 가져오기 (충분한 계산을 위해 150일치 수집)
        df = await fetch_ohlcv(ticker, interval="1d", period="150d")
        if df.empty or len(df) < 60:
            return {
                "ticker": ticker, "score": 0.0, "vcp_triggered": False,
                "vud_ratio": 1.0, "squeeze_pct": 100.0, "obv_divergence": 0.0,
                "close": 0.0, "change_pct": 0.0, "reason": "데이터 부족 (최소 60거래일 필요)"
            }

        # 2. 기초 시세 피드
        close_series = df['Close'].squeeze()
        high_series = df['High'].squeeze()
        low_series = df['Low'].squeeze()
        volume_series = df['Volume'].squeeze()
        
        current_close = float(close_series.iloc[-1])
        prev_close = float(close_series.iloc[-2])
        change_pct = round(((current_close - prev_close) / prev_close) * 100, 2)

        # 3. 추세 필터 (장기 추세가 무너진 역배열 종목은 폭발력이 떨어짐)
        ema50 = calculate_ema(close_series, 50)
        ema100 = calculate_ema(close_series, 100)
        
        is_bullish_trend = bool(current_close > ema50.iloc[-1])
        
        # 4. [지표 A] 마크 미너비니 VCP 패턴 진폭 축소 포착 (최대 25점)
        vcp_triggered = detect_vcp_pattern(df)
        vcp_score = 25.0 if vcp_triggered else 0.0
        
        # VCP가 아직 완성 안 됐더라도 진폭이 축소 중이면 보너스 점수 부여
        if not vcp_triggered:
            _, squeeze_score_series = calculate_bb_squeeze(df, window=20, history_window=120)
            sq_val = float(squeeze_score_series.iloc[-1])
            if sq_val < 30.0:  # 밴드가 크게 수축 중
                vcp_score = 10.0

        # 5. [지표 B] 거래량 급감 비율 (Volume Dry-up / VUD) 감지 (최대 25점)
        vud_series = calculate_volume_dryup(df, window=20)
        current_vud = float(vud_series.iloc[-1])
        
        # 거래량이 최근 20일 평균 대비 메마를수록 가점 (매수 대기 물량이 쪼그라든 임계점)
        if current_vud <= 0.35:     # 극도로 메마름 (거래량 35% 이하)
            vud_score = 25.0
        elif current_vud <= 0.60:   # 양호한 조임 (거래량 60% 이하)
            vud_score = 15.0
        elif current_vud <= 0.85:   # 약한 조임 (거래량 85% 이하)
            vud_score = 5.0
        else:
            vud_score = 0.0

        # 6. [지표 C] OBV 누적 매집 다이버전스 연산 (최대 25점)
        obv_div_series = calculate_obv_divergence(df, window=10)
        current_obv_div = float(obv_div_series.iloc[-1])
        
        # OBV 다이버전스 점수 매핑 (기울기 차이가 클수록 고득점)
        obv_score = round(current_obv_div * 0.25, 1)

        # 7. [지표 D] 볼린저 밴드 스퀴즈 수축도 산출 (최대 25점)
        _, squeeze_score_series = calculate_bb_squeeze(df, window=20, history_window=120)
        current_squeeze_score = float(squeeze_score_series.iloc[-1]) # 0%에 가까울수록 역사적 대압착
        
        # 수축도가 높을수록 고점 부여 (0% => 25점, 100% => 0점)
        squeeze_score = round((100.0 - current_squeeze_score) * 0.25, 1)

        # 8. 종합 점수 집계 (0~100점)
        total_score = vcp_score + vud_score + obv_score + squeeze_score
        
        # 역배열/하락 추세 종목은 2차 패널티 부여 (상승 추세가 아닌 횡보/하락장에서의 매집은 기회비용 소모)
        # 잦은 휩소나 종목 소멸을 막기 위해 기존 -35점에서 -15점으로 완화 (Task 10)
        if not is_bullish_trend:
            total_score = max(0.0, total_score - 15.0)

        # 최종 가중점수 반올림
        total_score = round(total_score, 1)

        return {
            "ticker": ticker,
            "score": total_score,
            "vcp_triggered": vcp_triggered,
            "vud_ratio": round(current_vud, 2),
            "squeeze_pct": round(current_squeeze_score, 1),
            "obv_divergence": round(current_obv_div, 1),
            "close": current_close,
            "change_pct": change_pct,
            "is_bullish_trend": is_bullish_trend
        }
    except Exception as e:
        logger.error(f"[SwingPredictor] Error analyzing {ticker}: {e}")
        return {
            "ticker": ticker, "score": 0.0, "vcp_triggered": False,
            "vud_ratio": 1.0, "squeeze_pct": 100.0, "obv_divergence": 0.0,
            "close": 0.0, "change_pct": 0.0, "reason": f"오류 발생: {str(e)}"
        }

async def scan_next_day_candidates(tickers: list) -> list:
    """
    유저 관심종목 및 주도주 감시 리스트 전체에 대해
    '내일 상승 확률이 가장 높은 스윙 후보군 TOP 5'를 병렬 스캔하여 점수 높은 순으로 반환합니다.
    """
    if not tickers:
        return []
        
    tasks = [analyze_swing_setup(ticker) for ticker in tickers]
    results = await asyncio.gather(*tasks)
    
    # 1. 유효한 점수를 가진 결과만 필터링
    valid_results = [r for r in results if r["score"] > 0]
    
    # 2. 내일 상승 예측 스코어 내림차순 정렬 (점수가 높을수록 세력 매집 완벽 단계)
    sorted_results = sorted(valid_results, key=lambda x: x["score"], reverse=True)
    
    # 3. 최대 5개 종목만 엄선
    return sorted_results[:5]
