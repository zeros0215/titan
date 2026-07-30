from abc import ABC, abstractmethod
from datetime import datetime, timedelta


class MarketCalendar(ABC):
    @abstractmethod
    def is_session(self, value: datetime) -> bool:
        raise NotImplementedError

    def session_count(self, start_exclusive: datetime, end_inclusive: datetime) -> int:
        if end_inclusive <= start_exclusive:
            return 0
        count = 0
        current = start_exclusive + timedelta(days=1)
        while current.date() <= end_inclusive.date():
            if self.is_session(current):
                count += 1
            current += timedelta(days=1)
        return count


class WeekdayMarketCalendar(MarketCalendar):
    """Conservative offline calendar; optional holidays make it exchange-aware."""

    def __init__(self, holidays: set | None = None) -> None:
        self.holidays = {
            item.date() if isinstance(item, datetime) else item
            for item in (holidays or set())
        }

    def is_session(self, value: datetime) -> bool:
        return value.weekday() < 5 and value.date() not in self.holidays


class CachedMarketCalendar(WeekdayMarketCalendar):
    """KIS-backed calendar with persistent cache and weekday fallback."""

    def __init__(self, provider, cache) -> None:
        super().__init__()
        self.provider = provider
        self.cache = cache
        self.sessions = cache.load()
        self.last_fallback_reason: str | None = None
        self.refresh_attempted = False

    def is_session(self, value: datetime) -> bool:
        known = self.sessions.get(value.date())
        return known if known is not None else super().is_session(value)

    def session_count(self, start_exclusive: datetime, end_inclusive: datetime) -> int:
        if end_inclusive <= start_exclusive:
            return 0
        start = (start_exclusive + timedelta(days=1)).date()
        end = end_inclusive.date()
        refresh_start = max(start, end - timedelta(days=70))
        missing = [
            day
            for day in self._dates(refresh_start, end)
            if day not in self.sessions
        ]
        if missing and not self.refresh_attempted:
            self.refresh_attempted = True
            try:
                fetched = self.provider.get_sessions(min(missing), max(missing))
                self.sessions.update(fetched)
                self.cache.save(self.sessions)
                self.last_fallback_reason = None
            except Exception as error:
                self.last_fallback_reason = f"{type(error).__name__}: {error}"
        return super().session_count(start_exclusive, end_inclusive)

    @staticmethod
    def _dates(start, end):
        current = start
        while current <= end:
            yield current
            current += timedelta(days=1)
