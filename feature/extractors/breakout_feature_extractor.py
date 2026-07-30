from feature.feature import Feature
from feature.feature_type import FeatureType


class BreakoutFeatureExtractor:

    def extract(
        self,
        stock
    ) -> Feature:

        price = stock.close
        high20 = max(stock.high[-20:])

        ratio = price / high20

        enabled = ratio >= 1.0

        strength = min(
            max(ratio - 0.98, 0.0) / 0.02,
            1.0
        )

        return Feature(
            type=FeatureType.BREAKOUT,
            enabled=enabled,
            strength=strength,
            value=ratio,
            reason=f"20일 고점 대비 {ratio:.3f}"
        )