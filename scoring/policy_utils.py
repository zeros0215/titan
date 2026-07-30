from feature.feature import Feature


class PolicyUtils:

    @staticmethod
    def feature_score(
        feature: Feature | None,
        max_score: int = 20
    ) -> int:

        if feature is None:
            return 0

        if not feature.enabled:
            return 0

        # Feature extractors decide whether their condition is meaningful enough
        # to be enabled.  The score budget represents corroborating conditions,
        # not the raw distance from a moving average or a price ratio.  Applying
        # that raw ratio once more made ordinary valid trends score near zero.
        return max_score
