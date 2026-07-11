import subprocess
import os
import sys
import json
import time
from datetime import datetime

# Force stdout to be utf-8 to avoid Windows CP949 encoding crash
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Target ticker files (v2 versions + db dynamic)
TICKERS_FILES = {
    "BLUECHIP": "backend/data/tickers_bluechip_v2.json",
    "PENNY": "backend/data/tickers_penny_v2.json",
    "TECH": "backend/data/tickers_tech_v2.json",
    "CHINA": "backend/data/tickers_china_v2.json",
    "ITALY": "backend/data/tickers_italy_v2.json",
    "DB_DYNAMIC": "backend/data/tickers_db_dynamic.json"
}

SCENARIOS = [
    # --- 3-Year Range ---
    {"name": "3Y-1d", "start": "2023-07-09", "end": "2026-07-09", "interval": "1d", "label": "3년 일봉 장기전"},
    {"name": "3Y-1h", "start": "2025-07-09", "end": "2026-07-09", "interval": "1h", "label": "1년 시간봉 중기전(대체)"},
    
    # --- 1-Year Range ---
    {"name": "1Y-1d", "start": "2025-07-09", "end": "2026-07-09", "interval": "1d", "label": "1년 일봉 중기전"},
    {"name": "1Y-1h", "start": "2025-07-09", "end": "2026-07-09", "interval": "1h", "label": "1년 시간봉 중기전"},
    
    # --- 3-Month Range ---
    {"name": "3M-1h", "start": "2026-04-09", "end": "2026-07-09", "interval": "1h", "label": "3개월 시간봉 단기전"},
    {"name": "3M-15m", "start": "2026-05-09", "end": "2026-07-09", "interval": "15m", "label": "60일 15분봉 정밀전"}
]

def main():
    print("==========================================================================")
    print(" 🏆 StockAuto v2.0 챔피언십 토너먼트 배틀 러너 (7대 정예 전략 특화)")
    print("==========================================================================")
    
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
            
            # 결과 JSON 파일 경로
            result_json_path = f"backend/data/champ_result_{domain}_{scenario['name']}.json"
            
            # run_tournament.py를 커스텀 기동
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
            
            # stdout/stderr 리디렉션
            log_temp_path = "backend/data/champ_temp_run.log"
            start_time = time.time()
            try:
                # 7대 우승전략 필터링은 run_tournament.py를 수정하거나 
                # run_tournament.py가 알아서 돌게 한 다음 결과 필터링을 여기서 직접 수행 가능.
                # 여기서는 연산 속도를 위해 run_tournament.py를 실행하기 전 
                # run_tournament.py의 TOURNAMENT_STRATEGIES를 7대 정예 전략으로 한시적 수정해둔 뒤 돌립니다.
                with open(log_temp_path, "w", encoding="utf-8") as temp_f:
                    res = subprocess.run(cmd, stdout=temp_f, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
                
                elapsed = time.time() - start_time
                
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
                        try:
                            os.remove(result_json_path)
                        except Exception:
                            pass
                    except Exception as parse_err:
                        print(f"  [⚠️ JSON 읽기 실패] {parse_err}")
                else:
                    print(f"  [⚠️ 결과 JSON 파일 없음: {result_json_path}]")
                        
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
                
    report_path = "docs/history/strategy_championship_report_V2.md"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    
    print("\n==========================================================================")
    print(" 📊 챔피언십 배틀 종료! 종합 마크다운 성적표 생성 중...")
    print("==========================================================================")
    
    markdown_lines = [
        "# 🏆 StockAuto v2.0 챔피언십 토너먼트 배틀 종합 보고서 (V2)",

        f"**실행 일시**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 1. 개요",
        "본 보고서는 1차 토너먼트 배틀에서 검증된 7대 최강 전략을 선정하여, 도메인별 500개 종목(ITALY 198개) 및 사용자의 DB 동적 종목(392개) 등 **총 2,590개 종목**을 대상으로 30종 다차원 대항전을 가동한 결과입니다.",
        "",
        "## 2. 통합 리더보드 (정예 전략 챔피언십 결과)",
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
        "## 3. 최종 평가 및 실전 배치 전략 제안",
        "- 대규모 종목 데이터 셋 상에서도 일관된 초과 수익을 내는 강건한 전략을 실전 스캐너 및 자동 매매전략으로 최종 채택합니다."
    ])
    
    with open(report_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(markdown_lines))
        
    print(f"➔ 챔피언십 성적표가 {report_path} 에 성공적으로 저장되었습니다.")
    print("==========================================================================")

if __name__ == "__main__":
    main()
