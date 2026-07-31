"""Immutable research profiles layered on the frozen V1 selection rules."""

from dataclasses import dataclass, replace

from config.selection_criteria import SELECTION_CRITERIA, SelectionCriteria


@dataclass(frozen=True, slots=True)
class StrategyProfile:
    version: str
    criteria: SelectionCriteria
    maximum_entry_gap: float | None
    recommended_holding_sessions: int
    selection_limit: int = 5
    profit_target: float | None = None
    stop_loss: float | None = None
    maximum_holding_sessions: int | None = None


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
        use_market_regime_rules=True,
    ),
    maximum_entry_gap=0.03,
    recommended_holding_sessions=5,
)

V1_3_S78_N7_CANDIDATE = StrategyProfile(
    version="V1.3-S78-N7-CANDIDATE",
    criteria=replace(
        SELECTION_CRITERIA,
        minimum_score=78,
        reject_combined_volatility_warnings=True,
        require_acceleration_or_volume_surge=True,
        use_market_regime_rules=True,
    ),
    maximum_entry_gap=0.03,
    recommended_holding_sessions=5,
    selection_limit=7,
)

V1_3_S78_N7_TP5_SL10_CANDIDATE = StrategyProfile(
    version="V1.3-S78-N7-TP5-SL10-CANDIDATE",
    criteria=V1_3_S78_N7_CANDIDATE.criteria,
    maximum_entry_gap=0.03,
    recommended_holding_sessions=20,
    selection_limit=7,
    profit_target=0.05,
    stop_loss=0.10,
    maximum_holding_sessions=20,
)

V1_3_S80_N7_TP5_SL10_CANDIDATE = StrategyProfile(
    version="V1.3-S80-N7-TP5-SL10-CANDIDATE",
    criteria=replace(
        V1_3_S78_N7_CANDIDATE.criteria,
        minimum_score=80,
        strong_score_adjustment=0,
    ),
    maximum_entry_gap=0.03,
    recommended_holding_sessions=20,
    selection_limit=7,
    profit_target=0.05,
    stop_loss=0.10,
    maximum_holding_sessions=20,
)

V1_3_S79_N2_TP5_SL10_CANDIDATE = StrategyProfile(
    version="V1.3-S79-N2-TP5-SL10-CANDIDATE",
    criteria=replace(
        V1_3_S80_N7_TP5_SL10_CANDIDATE.criteria,
        minimum_score=79,
        sideways_score_adjustment=0,
    ),
    maximum_entry_gap=0.03,
    recommended_holding_sessions=20,
    selection_limit=2,
    profit_target=0.05,
    stop_loss=0.10,
    maximum_holding_sessions=20,
)

V1_3_DUAL_5D_S80_N7_TP5_SL10_CANDIDATE = StrategyProfile(
    version="V1.3-DUAL-5D-S80-N7-TP5-SL10-CANDIDATE",
    criteria=replace(
        V1_3_S80_N7_TP5_SL10_CANDIDATE.criteria,
        use_short_term_market_overlay=True,
    ),
    maximum_entry_gap=0.03,
    recommended_holding_sessions=20,
    selection_limit=7,
    profit_target=0.05,
    stop_loss=0.10,
    maximum_holding_sessions=20,
)

STRATEGY_PROFILES = {
    profile.version: profile
    for profile in (
        V1_1,
        V1_2_CANDIDATE,
        V1_2_GAP_CANDIDATE,
        V1_2_5D_CANDIDATE,
        V1_3_RISK_5D_CANDIDATE,
        V1_3_S78_N7_CANDIDATE,
        V1_3_S78_N7_TP5_SL10_CANDIDATE,
        V1_3_S80_N7_TP5_SL10_CANDIDATE,
        V1_3_S79_N2_TP5_SL10_CANDIDATE,
        V1_3_DUAL_5D_S80_N7_TP5_SL10_CANDIDATE,
    )
}


def get_strategy_profile(version: str) -> StrategyProfile:
    try:
        return STRATEGY_PROFILES[version]
    except KeyError as exc:
        raise ValueError(f"지원하지 않는 전략 버전입니다: {version}") from exc
