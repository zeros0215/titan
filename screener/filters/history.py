class HistoryFilter:

    MIN_CANDLES = 250

    def check(self, series):

        return len(series.candles) >= self.MIN_CANDLES