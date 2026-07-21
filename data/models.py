from dataclasses import dataclass
from datetime import datetime



@dataclass
class StockInfo:


    ticker:str

    name:str



@dataclass
class StockPrice:


    date:datetime

    open:float

    high:float

    low:float

    close:float

    volume:int



@dataclass
class ScoreResult:


    trend_score:int = 0

    volume_score:int = 0

    trading_score:int = 0

    momentum_score:int = 0

    breakout_score:int = 0

    risk_penalty:int = 0



@dataclass
class AnalysisResult:


    ticker:str

    name:str

    price:float

    total_score:int

    grade:str