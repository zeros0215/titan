from abc import ABC, abstractmethod



class MarketProvider(ABC):


    @abstractmethod
    def get_daily_price(
        self,
        ticker:str
    ):

        """
        일봉 데이터 조회

        return:
            DataFrame
        """

        pass