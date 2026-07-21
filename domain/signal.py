"""
Signal Domain Model
"""

from dataclasses import dataclass, field

from domain.enums import SignalType


@dataclass(slots=True)
class Signal:

    signal_type: SignalType

    name: str

    passed: bool

    description: str = ""


@dataclass(slots=True)
class SignalResult:

    signals: list[Signal] = field(default_factory=list)

    def add(self, signal: Signal) -> None:
        self.signals.append(signal)

    @property
    def passed_signals(self) -> list[Signal]:
        return [s for s in self.signals if s.passed]

    @property
    def failed_signals(self) -> list[Signal]:
        return [s for s in self.signals if not s.passed]