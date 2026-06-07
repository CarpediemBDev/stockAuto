import argparse
import asyncio
import json
from datetime import date
from pathlib import Path

from app.bot.backtest_engine import BacktestSimulator
from app.bot.walk_forward import WalkForwardConfig, run_walk_forward_evaluation
from run_tournament import TOURNAMENT_STRATEGIES


class SharedWindowRunner:
    def __init__(
        self,
        tickers: list[str],
        interval: str,
        initial_cash: float,
    ):
        self.tickers = tickers
        self.interval = interval
        self.initial_cash = initial_cash
        self._prepared_windows: dict[tuple[date, date], BacktestSimulator] = {}

    async def __call__(
        self,
        strategy_type: str,
        start_date: date,
        end_date: date,
    ) -> dict:
        window_key = (start_date, end_date)
        base_simulator = self._prepared_windows.get(window_key)
        if base_simulator is None:
            base_simulator = BacktestSimulator(
                tickers=self.tickers,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                interval=self.interval,
                initial_cash=self.initial_cash,
                strategy_type="regime_switching",
            )
            await base_simulator.prepare_data()
            self._prepared_windows[window_key] = base_simulator

        simulator = BacktestSimulator(
            tickers=self.tickers,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            interval=self.interval,
            initial_cash=self.initial_cash,
            strategy_type=strategy_type,
        )
        simulator.tickers_data = base_simulator.tickers_data
        simulator.qqq_data = base_simulator.qqq_data
        simulator.processed_metrics = base_simulator.processed_metrics
        simulator.qqq_metrics = base_simulator.qqq_metrics
        simulator.timeline = base_simulator.timeline
        return simulator.run()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="StockAuto 전략 Walk-Forward 아웃오브샘플 평가기",
    )
    parser.add_argument("--start", required=True, help="전체 평가 시작일 YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="전체 평가 종료일 YYYY-MM-DD")
    parser.add_argument("--train-days", type=int, default=180)
    parser.add_argument("--test-days", type=int, default=60)
    parser.add_argument("--step-days", type=int, default=60)
    parser.add_argument("--select-count", type=int, default=10)
    parser.add_argument("--minimum-trades", type=int, default=15)
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--initial-cash", type=float, default=10000.0)
    parser.add_argument(
        "--strategies",
        nargs="*",
        choices=sorted(TOURNAMENT_STRATEGIES),
        help="평가할 전략 키. 생략하면 전체 등록 전략을 평가합니다.",
    )
    parser.add_argument(
        "--tickers-file",
        default="tickers.json",
        help="backend 기준 티커 JSON 파일 경로",
    )
    parser.add_argument(
        "--output",
        default="walk_forward_report.json",
        help="backend 기준 결과 JSON 경로",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_arguments()
    tickers_path = Path(args.tickers_file)
    with tickers_path.open("r", encoding="utf-8") as file:
        tickers = [item["ticker"] for item in json.load(file)]

    config = WalkForwardConfig(
        train_days=args.train_days,
        test_days=args.test_days,
        step_days=args.step_days,
        select_count=args.select_count,
        minimum_trades=args.minimum_trades,
    )
    runner = SharedWindowRunner(
        tickers=tickers,
        interval=args.interval,
        initial_cash=args.initial_cash,
    )
    strategy_types = args.strategies or list(TOURNAMENT_STRATEGIES)
    result = await run_walk_forward_evaluation(
        strategy_types=strategy_types,
        start_date=date.fromisoformat(args.start),
        end_date=date.fromisoformat(args.end),
        runner=runner,
        config=config,
    )

    output_path = Path(args.output)
    with output_path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(result, file, ensure_ascii=False, indent=2, default=str)

    print(f"Walk-Forward 창: {result['window_count']}개")
    print(f"결과 파일: {output_path.resolve()}")
    print("상위 아웃오브샘플 전략:")
    for rank, row in enumerate(result["leaderboard"][: args.select_count], 1):
        print(
            f"{rank:>2}. {row['strategy_type']}"
            f" | 선택률 {row['selection_rate']:.2f}%"
            f" | 수익 구간 {row['profitable_window_rate']:.2f}%"
            f" | 중앙 OOS 수익률 {row['median_test_return']:+.2f}%"
        )


if __name__ == "__main__":
    asyncio.run(main())
