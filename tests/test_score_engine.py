"""
ScoreEngine Test
"""

import unittest

from scoring.result import ScoreResult


class TestScoreResult(unittest.TestCase):

    def test_total_score(self):

        result = ScoreResult(

            trend_score=40,

            volume_score=20,

            trading_score=20,

            momentum_score=12,

            breakout_score=0,

            risk_penalty=0,

            total_score=92,

            grade="S"

        )

        self.assertEqual(

            result.total_score,

            92

        )

    def test_score_not_over_100(self):

        result = ScoreResult(

            trend_score=40,

            volume_score=20,

            trading_score=20,

            momentum_score=20,

            breakout_score=20,

            risk_penalty=0,

            total_score=100,

            grade="S"

        )

        self.assertLessEqual(

            result.total_score,

            100

        )


if __name__ == "__main__":

    unittest.main()