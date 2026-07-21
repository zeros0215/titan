class DataCollector:


    def __init__(
        self,
        market_provider
    ):

        self.market = market_provider



    def collect(
        self,
        ticker
    ):


        return (

            self.market
            .get_daily_price(
                ticker
            )

        )