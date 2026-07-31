import unittest

from config.selection_criteria import SELECTION_CRITERIA
from config.strategy_profiles import (
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


class StrategyProfilesTest(unittest.TestCase):
    def test_v1_1_keeps_frozen_selection_criteria(self):
        self.assertIs(V1_1.criteria, SELECTION_CRITERIA)
        self.assertIsNone(V1_1.maximum_entry_gap)
        self.assertEqual(V1_1.recommended_holding_sessions, 1)

    def test_v1_2_candidate_is_isolated(self):
        self.assertIsNot(V1_2_CANDIDATE.criteria, SELECTION_CRITERIA)
        self.assertEqual(
            V1_2_CANDIDATE.criteria.minimum_market_strength,
            0.65,
        )
        self.assertEqual(
            V1_2_CANDIDATE.criteria.maximum_momentum_5d,
            10.0,
        )
        self.assertEqual(V1_2_CANDIDATE.maximum_entry_gap, 0.01)
        self.assertEqual(V1_2_CANDIDATE.recommended_holding_sessions, 5)

    def test_gap_candidate_changes_entry_only(self):
        self.assertIs(V1_2_GAP_CANDIDATE.criteria, SELECTION_CRITERIA)
        self.assertEqual(V1_2_GAP_CANDIDATE.maximum_entry_gap, 0.03)
        self.assertEqual(
            V1_2_GAP_CANDIDATE.recommended_holding_sessions,
            5,
        )

    def test_5d_candidate_changes_holding_policy_only(self):
        self.assertIs(V1_2_5D_CANDIDATE.criteria, SELECTION_CRITERIA)
        self.assertIsNone(V1_2_5D_CANDIDATE.maximum_entry_gap)
        self.assertEqual(V1_2_5D_CANDIDATE.recommended_holding_sessions, 5)

    def test_risk_5d_candidate_adds_hard_confirmation_rules(self):
        criteria = V1_3_RISK_5D_CANDIDATE.criteria
        self.assertTrue(criteria.reject_combined_volatility_warnings)
        self.assertTrue(criteria.require_acceleration_or_volume_surge)
        self.assertTrue(criteria.use_market_regime_rules)
        self.assertEqual(V1_3_RISK_5D_CANDIDATE.maximum_entry_gap, 0.03)
        self.assertEqual(
            V1_3_RISK_5D_CANDIDATE.recommended_holding_sessions,
            5,
        )

    def test_s78_n7_keeps_risk_rules_and_expands_selection(self):
        criteria = V1_3_S78_N7_CANDIDATE.criteria
        self.assertEqual(criteria.minimum_score, 78)
        self.assertTrue(criteria.reject_combined_volatility_warnings)
        self.assertTrue(criteria.require_acceleration_or_volume_surge)
        self.assertTrue(criteria.use_market_regime_rules)
        self.assertEqual(V1_3_S78_N7_CANDIDATE.maximum_entry_gap, 0.03)
        self.assertEqual(V1_3_S78_N7_CANDIDATE.selection_limit, 7)

    def test_tp5_candidate_uses_bounded_profit_target_exit(self):
        profile = V1_3_S78_N7_TP5_SL10_CANDIDATE
        self.assertIs(profile.criteria, V1_3_S78_N7_CANDIDATE.criteria)
        self.assertEqual(profile.profit_target, 0.05)
        self.assertEqual(profile.stop_loss, 0.10)
        self.assertEqual(profile.maximum_holding_sessions, 20)
        self.assertEqual(profile.recommended_holding_sessions, 20)

    def test_s80_candidate_never_relaxes_below_eighty(self):
        profile = V1_3_S80_N7_TP5_SL10_CANDIDATE
        self.assertEqual(80, profile.criteria.minimum_score)
        self.assertEqual(0, profile.criteria.strong_score_adjustment)
        self.assertEqual(0.05, profile.profit_target)
        self.assertEqual(0.10, profile.stop_loss)

    def test_s79_n2_candidate_is_controlled_relaxation(self):
        profile = V1_3_S79_N2_TP5_SL10_CANDIDATE
        self.assertEqual(79, profile.criteria.minimum_score)
        self.assertEqual(0, profile.criteria.sideways_score_adjustment)
        self.assertTrue(profile.criteria.use_market_regime_rules)
        self.assertEqual(2, profile.selection_limit)
        self.assertEqual(0.05, profile.profit_target)
        self.assertEqual(0.10, profile.stop_loss)

    def test_dual_market_candidate_enables_short_overlay(self):
        profile = V1_3_DUAL_5D_S80_N7_TP5_SL10_CANDIDATE
        self.assertTrue(profile.criteria.use_short_term_market_overlay)
        self.assertEqual(80, profile.criteria.minimum_score)
        self.assertEqual(7, profile.selection_limit)


if __name__ == "__main__":
    unittest.main()
