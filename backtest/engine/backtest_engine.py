"""
Selection Validation Engine
"""

from datetime import datetime

from backtest.model.backtest_result import BacktestResult
from backtest.model.selection import Selection
from backtest.model.selection_result import SelectionResult
from backtest.evaluator.return_evaluator import ReturnEvaluator
from backtest.transaction_cost import TransactionCostPolicy



class BacktestEngine:
    """
    Ranking 결과를 검증하는 엔진.

    거래를 수행하지 않는다.

    Analyzer가 선택한 종목이
    일정 기간 후 실제로 상승했는지를 검증한다.
    """

    def __init__(
        self,
        return_evaluator: ReturnEvaluator | None = None,
        transaction_cost_policy: TransactionCostPolicy | None = None,
    ) -> None:
        self.return_evaluator = return_evaluator or ReturnEvaluator()
        self.transaction_cost_policy = (
            transaction_cost_policy or TransactionCostPolicy()
        )

    def run(
        self,
        selections: list[Selection],
        holding_days: int,
        selection_prices: dict[str, float],
        evaluation_prices: dict[str, float],
        evaluation_date: datetime,
        market_context: bool = False,
        benchmark_returns: dict[str, float] | None = None,
    ) -> BacktestResult:

        if holding_days <= 0:
            raise ValueError("holding_days must be greater than zero")

        results: list[SelectionResult] = []
        missing_price_codes: list[str] = []

        for selection in selections:
            if evaluation_date < selection.selected_date:
                raise ValueError(
                    "evaluation_date must not be before selection_date"
                )

            code = selection.code

            if (
                code not in selection_prices
                or code not in evaluation_prices
            ):
                missing_price_codes.append(code)
                continue

            selection_price = selection_prices[code]
            evaluation_price = evaluation_prices[code]

            return_rate = self.return_evaluator.evaluate(
                selection_price,
                evaluation_price,
            )
            net_return_rate = self.transaction_cost_policy.net_return(
                selection_price,
                evaluation_price,
            )
            benchmark_return_rate = None
            if benchmark_returns is not None:
                benchmark_return_rate = benchmark_returns.get(code)
                if (
                    benchmark_return_rate is None
                    and selection.analysis.market is not None
                ):
                    benchmark_return_rate = benchmark_returns.get(
                        selection.analysis.market.value
                    )
            excess_return_rate = (
                net_return_rate - benchmark_return_rate
                if benchmark_return_rate is not None
                else None
            )

            results.append(
                SelectionResult(
                    selection=selection,
                    evaluation_date=evaluation_date,
                    holding_days=holding_days,
                    selection_price=selection_price,
                    evaluation_price=evaluation_price,
                    return_rate=return_rate,
                    net_return_rate=net_return_rate,
                    benchmark_return_rate=benchmark_return_rate,
                    excess_return_rate=excess_return_rate,
                )
            )

        return BacktestResult(
            results=results,
            missing_price_codes=missing_price_codes,
        )
