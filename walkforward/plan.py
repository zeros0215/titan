from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(slots=True, frozen=True)
class WalkForwardFold:
    index: int
    training_start: datetime
    training_end: datetime
    test_start: datetime
    test_end: datetime

    def selection_dates(
        self, interval_months: int, interval_days: int | None = None,
    ) -> list[datetime]:
        if interval_days is not None:
            if interval_days <= 0:
                raise ValueError("interval_days must be greater than zero")
            dates = []
            current = datetime(
                self.test_start.year, self.test_start.month, self.test_start.day
            )
            while current.weekday() >= 5:
                current += timedelta(days=1)
            while current <= self.test_end:
                if current.weekday() < 5:
                    dates.append(current)
                current += timedelta(days=interval_days)
            return dates
        if interval_months <= 0:
            raise ValueError("interval_months must be greater than zero")
        dates = []
        year, month = self.test_start.year, self.test_start.month
        current = datetime(year, month, 1)
        while current <= self.test_end:
            dates.append(current)
            month += interval_months
            year += (month - 1) // 12
            month = (month - 1) % 12 + 1
            current = datetime(year, month, 1)
        return dates


@dataclass(slots=True, frozen=True)
class WalkForwardPlan:
    folds: list[WalkForwardFold]

    @classmethod
    def expanding_years(
        cls,
        history_start_year: int,
        first_test_year: int,
        last_test_year: int,
    ) -> "WalkForwardPlan":
        if history_start_year >= first_test_year:
            raise ValueError("history_start_year must be before first_test_year")
        if last_test_year < first_test_year:
            raise ValueError("last_test_year must not be before first_test_year")
        return cls([
            WalkForwardFold(
                index=index,
                training_start=datetime(history_start_year, 1, 1),
                training_end=datetime(year - 1, 12, 31, 23, 59, 59),
                test_start=datetime(year, 1, 1),
                test_end=datetime(year, 12, 31, 23, 59, 59),
            )
            for index, year in enumerate(
                range(first_test_year, last_test_year + 1),
                start=1,
            )
        ])
