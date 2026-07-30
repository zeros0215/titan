import unittest

from config.selection_criteria import SELECTION_CRITERIA
from config.strategy_profiles import (
    V1_1,
    V1_2_CANDIDATE,
    V1_2_GAP_CANDIDATE,
    V1_2_5D_CANDIDATE,
    V1_3_RISK_5D_CANDIDATE,
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
        self.assertEqual(V1_3_RISK_5D_CANDIDATE.maximum_entry_gap, 0.03)
        self.assertEqual(
            V1_3_RISK_5D_CANDIDATE.recommended_holding_sessions,
            5,
        )


if __name__ == "__main__":
    unittest.main()
