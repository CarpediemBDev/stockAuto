import os
import sys
import time
import subprocess
from pathlib import Path
from datetime import datetime
from app.core.logging import logger

LOCK_FILE = Path(__file__).resolve().parents[2] / "data" / "off_market_run.lock"


def check_ram_safety() -> bool:
    """
    서버의 전체 RAM 사용량을 감시합니다.
    psutil 패키지 미설치 환경에서도 안전하게 호환되도록 구동합니다.
    """
    try:
        import psutil
        memory = psutil.virtual_memory()
        if memory.percent > 75.0:
            logger.warning(
                f"[Off-Market Task] RAM 사용량({memory.percent}%)이 "
                f"안전 기준(75.0%)을 초과하여 연산을 보류합니다."
            )
            return False
    except ImportError:
        # psutil 모듈이 없는 환경에서는 표준 라이브러리로 자율 통과
        pass
    except Exception as e:
        logger.error(f"[Off-Market Task] RAM 감시 중 예외 발생: {e}")
    return True


def acquire_pid_lock() -> bool:
    """중복 실행을 방지하기 위한 PID Lock을 생성합니다."""
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists():
        try:
            with open(LOCK_FILE, "r") as f:
                old_pid = int(f.read().strip())
            # 프로세스 생존 여부 표준 인스펙션
            try:
                os.kill(old_pid, 0)
                logger.warning(f"[Off-Market Task] 이미 프로세스 (PID: {old_pid})가 실행 중입니다. 안전 스킵합니다.")
                return False
            except (OSError, ProcessLookupError):
                pass # 프로세스가 이미 종료된 경우 락 파일 정화 후 재생성
        except Exception:
            pass

    try:
        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
        return True
    except Exception as e:
        logger.error(f"[Off-Market Task] PID Lock 생성 실패: {e}")
        return False


def release_pid_lock():
    """PID Lock을 안전하게 해제합니다."""
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
    except Exception as e:
        logger.error(f"[Off-Market Task] PID Lock 해제 실패: {e}")


def run_isolated_backtest_tournament(start_date: str = None, end_date: str = None):
    """
    메인 웹 서버 메모리 OOM을 100% 방지하기 위해
    독립된 서브프로세스(Subprocess)로 백테스트 아레나 연산을 실행합니다.
    """
    if not check_ram_safety():
        return False

    if not acquire_pid_lock():
        return False

    try:
        logger.info("[Off-Market Task] 독립 서브프로세스 기반 백테스트 토너먼트 연산을 구동합니다...")
        python_exe = sys.executable
        runner_script = Path(__file__).resolve().parents[1] / "admin" / "backtest_runner.py"
        
        cmd = [python_exe, str(runner_script)]
        if start_date and end_date:
            cmd.extend(["--start-date", start_date, "--end-date", end_date])

        # 독립 프로세스로 무소음 실행 및 타임아웃 10분 강제 설정
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        if result.returncode == 0:
            logger.info("[Off-Market Task] 백테스트 토너먼트 연산 및 캐시 적재 완료!")
            return True
        else:
            logger.error(f"[Off-Market Task] 백테스트 연산 프로세스 에러 (Exit Code {result.returncode}): {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("[Off-Market Task] 백테스트 연산 프로세스가 10분 타임아웃을 초과하여 강제 종료되었습니다.")
        return False
    except Exception as e:
        logger.error(f"[Off-Market Task] 서브프로세스 실행 중 예외 발생: {e}", exc_info=True)
        return False
    finally:
        release_pid_lock()


def run_after_hours_scanner_refresh():
    """에프터장 마감 직후 (06:00 KST) 상승 후보 종목 스캐너 무소음 백그라운드 갱신"""
    try:
        logger.info("[Off-Market Task] 에프터장 상승 후보 종목 스캐너 갱신을 시작합니다...")
        from app.scanner.after_hours_scanner import trigger_after_hours_refresh
        trigger_after_hours_refresh()
        logger.info("[Off-Market Task] 에프터장 상승 후보 종목 갱신 완료!")
    except Exception as e:
        logger.error(f"[Off-Market Task] 에프터장 스캐너 갱신 중 에러: {e}", exc_info=True)


def run_swing_prediction_refresh():
    """스윙 예측 지표 스냅샷 무소음 갱신"""
    try:
        logger.info("[Off-Market Task] 스윙 예측 지표 스냅샷 갱신을 시작합니다...")
        from app.scanner.swing_prediction_cache import refresh_swing_prediction_cache
        refresh_swing_prediction_cache()
        logger.info("[Off-Market Task] 스윙 예측 지표 스냅샷 갱신 완료!")
    except Exception as e:
        logger.error(f"[Off-Market Task] 스윙 예측 스냅샷 갱신 중 에러: {e}", exc_info=True)
