from broker.kis.market_api import KisMarketApi
from broker.kis.mapper.daily_price_mapper import DailyPriceMapper
from broker.kis.mapper.candle_mapper import CandleMapper
from broker.kis.session import KisSession


def main():

    session = KisSession()

    api = KisMarketApi(session)

    data = api.get_daily_price("005930")

    dto_list = DailyPriceMapper.to_list(data)

    candles = CandleMapper.to_domain_list(dto_list)

    print(candles[0])

    session.close()


if __name__ == "__main__":
    main()