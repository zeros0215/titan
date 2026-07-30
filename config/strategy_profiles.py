"""Immutable research profiles layered on the frozen V1 selection rules."""

from dataclasses import dataclass, replace

from config.selection_criteria import SELECTION_CRITERIA, SelectionCriteria


@dataclass(frozen=True, slots=True)
class StrategyProfile:
    version: str
    criteria: SelectionCriteria
    maximum_entry_gap: float | None
    recommended_holding_sessions: int


V1_1 = StrategyProfile(
    version="V1.1",
    criteria=SELECTION_CRITERIA,
    maximum_entry_gap=None,
    recommended_holding_sessions=1,
)

V1_2_CANDIDATE = StrategyProfile(
    version="V1.2-CANDIDATE",
    criteria=replace(
        SELECTION_CRITERIA,
        minimum_market_strength=0.65,
        maximum_momentum_5d=10.0,
    ),
    maximum_entry_gap=0.01,
    recommended_holding_sessions=5,
)

V1_2_GAP_CANDIDATE = StrategyProfile(
    version="V1.2-GAP-CANDIDATE",
    criteria=SELECTION_CRITERIA,
    maximum_entry_gap=0.03,
    recommended_holding_sessions=5,
)

V1_2_5D_CANDIDATE = StrategyProfile(
    version="V1.2-5D-CANDIDATE",
    criteria=SELECTION_CRITERIA,
    maximum_entry_gap=None,
    recommended_holding_sessions=5,
)

V1_3_RISK_5D_CANDIDATE = StrategyProfile(
    version="V1.3-RISK-5D-CANDIDATE",
    criteria=replace(
        SELECTION_CRITERIA,
        reject_combined_volatility_warnings=True,
        require_acceleration_or_volume_surge=True,
    ),
    maximum_entry_gap=0.03,
    recommended_holding_sessions=5,
)

STRATEGY_PROFILES = {
    profile.version: profile
    for profile in (
        V1_1,
        V1_2_CANDIDATE,
        V1_2_GAP_CANDIDATE,
        V1_2_5D_CANDIDATE,
        V1_3_RISK_5D_CANDIDATE,
    )
}


def get_strategy_profile(version: str) -> StrategyProfile:
    try:
        return STRATEGY_PROFILES[version]
    except KeyError as exc:
        raise ValueError(f"지원하지 않는 전략 버전입니다: {version}") from exc
