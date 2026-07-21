from abc import ABC, abstractmethod



class Strategy(ABC):


    @abstractmethod
    def analyze(
        self,
        data
    ):

        """
        종목 분석 전략

        return:
            score data

        """

        pass