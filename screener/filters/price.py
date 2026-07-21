class PriceFilter:

    MIN_PRICE = 3000

    MAX_PRICE = 500000

    def check(self, series):

        price = series.latest.close

        return (

            self.MIN_PRICE

            <=

            price

            <=

            self.MAX_PRICE

        )