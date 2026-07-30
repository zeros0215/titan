import re
from collections import defaultdict
from datetime import date, timedelta

from universe_history.model import (
    IssueSeverity,
    UniverseHistoryIssue,
    UniverseHistoryValidation,
)


class UniverseHistoryValidator:
    CODE_PATTERN = re.compile(r"^[0-9A-Z]{6}$")

    def validate(
        self,
        records,
        coverage_start: date,
        coverage_end: date,
    ) -> UniverseHistoryValidation:
        issues = []
        if coverage_end < coverage_start:
            issues.append(self._error(
                "INVALID_COVERAGE",
                "coverage_end must be on or after coverage_start",
            ))
        seen = set()
        by_code = defaultdict(list)
        for record in records:
            key = (
                record.code,
                record.market.value,
                record.effective_from,
                record.effective_to,
            )
            if key in seen:
                issues.append(self._error(
                    "DUPLICATE_INTERVAL",
                    "duplicate market interval",
                    record.code,
                ))
            seen.add(key)
            by_code[record.code].append(record)
            if not self.CODE_PATTERN.fullmatch(record.code):
                issues.append(self._error(
                    "INVALID_CODE",
                    "code must contain six uppercase letters or digits",
                    record.code,
                ))
            if not record.name:
                issues.append(self._error(
                    "EMPTY_NAME",
                    "stock name is required",
                    record.code,
                ))
            if not record.source_id:
                issues.append(self._error(
                    "MISSING_SOURCE",
                    "source_id is required",
                    record.code,
                ))
            if (
                record.effective_to is not None
                and record.effective_to < record.effective_from
            ):
                issues.append(self._error(
                    "INVALID_INTERVAL",
                    "effective_to is before effective_from",
                    record.code,
                ))

        for code, items in by_code.items():
            ordered = sorted(items, key=lambda item: item.effective_from)
            for previous, current in zip(ordered, ordered[1:]):
                if (
                    previous.effective_to is None
                    or current.effective_from <= previous.effective_to
                ):
                    issues.append(self._error(
                        "OVERLAPPING_INTERVALS",
                        "one stock has overlapping market intervals",
                        code,
                    ))
                elif self._has_weekday_gap(
                    previous.effective_to,
                    current.effective_from,
                ):
                    issues.append(self._warning(
                        "INTERVAL_GAP",
                        "gap exists between stock market intervals",
                        code,
                    ))

        if not records:
            issues.append(self._error("EMPTY_HISTORY", "history has no records"))
        if records and min(item.effective_from for item in records) > coverage_start:
            issues.append(self._warning(
                "LATE_FIRST_RECORD",
                "earliest record begins after declared coverage start",
            ))
        return UniverseHistoryValidation(
            record_count=len(records),
            stock_count=len(by_code),
            issues=issues,
        )

    @staticmethod
    def _error(code, message, stock_code=None):
        return UniverseHistoryIssue(
            IssueSeverity.ERROR, code, message, stock_code
        )

    @staticmethod
    def _warning(code, message, stock_code=None):
        return UniverseHistoryIssue(
            IssueSeverity.WARNING, code, message, stock_code
        )

    @staticmethod
    def _has_weekday_gap(previous_end, current_start):
        current = previous_end + timedelta(days=1)
        while current < current_start:
            if current.weekday() < 5:
                return True
            current += timedelta(days=1)
        return False
