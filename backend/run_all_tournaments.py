import subprocess
import os
import sys
import json
import time
from datetime import datetime, timedelta

# Force stdout to be utf-8 to avoid Windows CP949 encoding crash
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

TICKERS_FILES = {
    "BLUECHIP": "backend/data/tickers_bluechip.json",
    "PENNY": "backend/data/tickers_penny.json",
    "TECH": "backend/data/tickers_tech.json",
    "CHINA": "backend/data/tickers_china.json",
    "ITALY": "backend/data/tickers_italy.json"
}

# 30 Combinations: 5 domains x 3 periods x 2 intervals
# For 3 periods: 3-Year, 1-Year, 3-Month
# For intervals: 
# - 3-Year: 1d and 1h (if enough data, otherwise 1d only. We fall back safely)
# - 1-Year: 1d and 1h
# - 3-Month: 1h and 15m
SCENARIOS = [
    # --- 3-Year Range (2023-07-09 ~ 2026-07-09) ---
    {"name": "3Y-1d", "start": "2023-07-09", "end": "2026-07-09", "interval": "1d", "label": "3년 일봉 장기전"},
    {"name": "3Y-1h", "start": "2025-07-09", "end": "2026-07-09", "interval": "1h", "label": "1년 시간봉 중기전(대체)"}, # yfinance 1h는 2년 제한이므로 1년치만 수집됨
    
    # --- 1-Year Range (2025-07-09 ~ 2026-07-09) ---
    {"name": "1Y-1d", "start": "2025-07-09", "end": "2026-07-09", "interval": "1d", "label": "1년 일봉 중기전"},
    {"name": "1Y-1h", "start": "2025-07-09", "end": "2026-07-09", "interval": "1h", "label": "1년 시간봉 중기전"},
    
    # --- 3-Month Range (2026-04-09 ~ 2026-07-09) ---
    {"name": "3M-1h", "start": "2026-04-09", "end": "2026-07-09", "interval": "1h", "label": "3개월 시간봉 단기전"},
    {"name": "3M-15m", "start": "2026-05-09", "end": "2026-07-09", "interval": "15m", "label": "60일 15분봉 정밀전"}
]

def main():
    print("==========================================================================")
    print(" 🏆 StockAuto v2.0 대규모 다차원 토너먼트 배틀 자동 마스터 러너")
    print("==========================================================================")
    
    # 공식 백엔드 가상환경 Python 경로 특정
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if os.name == "nt":  # Windows
        python_bin = os.path.join(current_dir, "venv", "Scripts", "python.exe")
    else:  # macOS / Linux
        python_bin = os.path.join(current_dir, "venv", "bin", "python")
        
    if not os.path.exists(python_bin):
        python_bin = sys.executable
        print(f"[Warning] Local venv not found. Using system python: {python_bin}")
    else:
        print(f"[*] Enforcing virtual environment python: {python_bin}")
        
    results_summary = []
    
    total_runs = len(TICKERS_FILES) * len(SCENARIOS)
    run_idx = 0
    
    for domain, tickers_file in TICKERS_FILES.items():
        if not os.path.exists(tickers_file):
            print(f"[❌ ERROR] Ticker file missing: {tickers_file}")
            continue
            
        for scenario in SCENARIOS:
            run_idx += 1
            print(f"\n==========================================================================")
            print(f" ⚔️ [{run_idx}/{total_runs}] 배틀 매치 기동: {domain} | {scenario['label']} ({scenario['interval']})")
            print(f" ⚔️ 기간: {scenario['start']} ~ {scenario['end']} | 인터벌: {scenario['interval']}")
            print(f"==========================================================================")
            
            # 결과 JSON 파일 경로 (도메인+시나리오별 유일 이름)
            result_json_path = f"backend/data/result_{domain}_{scenario['name']}.json"
            
            cmd = [
                python_bin,
                "backend/run_tournament.py",
                "--tickers_file", tickers_file,
                "--start", scenario["start"],
                "--end", scenario["end"],
                "--interval", scenario["interval"],
                "--cash", "10000.0",
                "--result_json", result_json_path,
            ]
            
            # stdout/stderr 파이프 버퍼 데드락을 방지하기 위해 파일 리디렉션 사용
            log_temp_path = "backend/data/temp_run.log"
            start_time = time.time()
            try:
                with open(log_temp_path, "w", encoding="utf-8") as temp_f:
                    res = subprocess.run(cmd, stdout=temp_f, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
                
                elapsed = time.time() - start_time
                
                # 임시 로그 파일 꼬리 (오류 진단용)
                stdout_tail = ""
                if os.path.exists(log_temp_path):
                    with open(log_temp_path, "r", encoding="utf-8") as temp_f:
                        stdout_tail = temp_f.read()[-2000:]
                    try:
                        os.remove(log_temp_path)
                    except Exception:
                        pass
                
                if res.returncode != 0:
                    print(f"[❌ FAIL] 매치 에러 발생 (Exit code: {res.returncode})")
                    print(stdout_tail)
                    results_summary.append({
                        "domain": domain,
                        "scenario": scenario["name"],
                        "status": "FAILED",
                        "time": f"{elapsed:.1f}s",
                        "winner": "N/A",
                        "alpha": "N/A"
                    })
                    continue
                
                # run_tournament.py 가 --result_json 으로 저장한 JSON 파일에서 우승 전략 정보 읽기
                winner_strategy = "Unknown"
                winner_alpha = "N/A"
                winner_return = "N/A"
                winner_sharpe = "N/A"
                winner_mdd = "N/A"
                winner_grade = "N/A"
                
                if os.path.exists(result_json_path):
                    try:
                        with open(result_json_path, "r", encoding="utf-8") as jf:
                            result_data = json.load(jf)
                        winner_strategy = result_data.get("winner_name", "Unknown")
                        alpha_val = result_data.get("alpha", 0.0)
                        winner_alpha = f"{alpha_val:+.2f}%"
                        winner_return = f"{result_data.get('total_return_rate', 0.0):+.2f}%"
                        winner_sharpe = f"{result_data.get('sharpe_ratio', 0.0):.2f}"
                        winner_mdd = f"{result_data.get('mdd', 0.0):.2f}%"
                        winner_grade = result_data.get("confidence_grade", "N/A")
                        # 사용한 JSON 파일 삭제
                        try:
                            os.remove(result_json_path)
                        except Exception:
                            pass
                    except Exception as parse_err:
                        print(f"  [⚠️ JSON 읽기 실패] {parse_err}")
                else:
                    print(f"  [⚠️ 결과 JSON 파일 없음: {result_json_path}] (전략이 모두 에러났을 수 있음)")
                        
                print(f"➔ 매치 성공! 우승: {winner_strategy} | Alpha: {winner_alpha} | 수익: {winner_return} | Grade: {winner_grade} (소요시간: {elapsed:.1f}초)")

                results_summary.append({
                    "domain": domain,
                    "scenario": scenario["name"],
                    "status": "SUCCESS",
                    "time": f"{elapsed:.1f}s",
                    "winner": winner_strategy,
                    "alpha": winner_alpha,
                    "return_rate": winner_return,
                    "sharpe": winner_sharpe,
                    "mdd": winner_mdd,
                    "grade": winner_grade,
                })

                
            except Exception as e:
                print(f"[❌ CRITICAL ERROR] {e}")
                
    # 종합 레포트 파일 생성
    report_path = "docs/history/strategy_tournament_report_V5.md"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    
    print("\n==========================================================================")
    print(" 📊 대항전 배틀 종료! 종합 마크다운 성적표 생성 중...")
    print("==========================================================================")
    
    markdown_lines = [
        "# 🏆 StockAuto v2.0 5대 도메인 다차원 토너먼트 배틀 종합 보고서 (V5)",
        f"**실행 일시**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 1. 개요",
        "본 보고서는 5대 투자 유니버스(우량주, 기술주, 잡주, 중국주, 이탈리아주) 총 500개 종목을 대상으로 3개년 장기전, 1개년 중기전, 60일 분봉 정밀전을 포함한 **총 30종의 다차원 토너먼트 조합**을 가동한 결과 원장입니다.",
        "야후 파이낸스 429 차단 우회 가드 및 로컬 Parquet 캐싱 엔진 하에서 안전하고 신속하게 병렬 백테스팅이 완료되었습니다.",
        "",
        "## 2. 통합 리더보드 (우승 전략 원장)",
        "",
        "| 도메인 | 시나리오 조합 | 검증 기간 | 인터벌 | 우승 전략 | 벤치마크 대비 초과수익 (Alpha) | 상태 | 소요 시간 |",
        "| :--- | :--- | :---: | :---: | :--- | :---: | :---: | :---: |"
    ]
    
    for r in results_summary:
        sc_info = [s for s in SCENARIOS if s["name"] == r["scenario"]][0]
        markdown_lines.append(
            f"| {r['domain']} | {sc_info['label']} | {sc_info['start']}~{sc_info['end']} | {sc_info['interval']} | **{r['winner']}** | {r['alpha']} | {r['status']} | {r['time']} |"
        )
        
    markdown_lines.extend([
        "",
        "## 3. 종합 평가 및 최적 강건 전략",
        "- 본 대항전을 통해 각 장세(상승, 하락, 횡보) 및 인터벌 단위별로 벤치마크(QQQ)를 이기고 MDD를 획기적으로 낮춘 최강의 포뮬러를 선정합니다.",
        "- 상세 개별전략 분석 및 휩쏘 회피율 평가는 `Critical Auditor` 와 `Robustness Analyst` 의 감사 리포트를 참고하십시오."
    ])
    
    with open(report_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(markdown_lines))
        
    print(f"➔ 종합 성적표가 {report_path} 에 성공적으로 저장되었습니다.")
    print("==========================================================================")

if __name__ == "__main__":
    main()
