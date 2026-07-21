import pandas as pd


# def filter_stock(code):

#     # --------------------------
#     # 우선주 제거
#     # --------------------------

#     if code.endswith("5"):
#         return False


#     # --------------------------
#     # ETF 제거
#     # --------------------------

#     # KODEX, TIGER 등 대부분
#     # 4자리 코드 패턴 제외

#     if code.startswith("4"):
#         return False


#     return True



from pykrx.stock import get_market_ticker_list
from pykrx.stock import get_market_ticker_name

def get_kospi_stocks():

    stocks = []

    tickers = get_market_ticker_list(market="KOSPI")

    for ticker in tickers:

        stocks.append({
            "ticker": ticker + ".KS",
            "name": get_market_ticker_name(ticker)
        })

    return stocks


# def get_kospi_stocks():

#     url = (
#         "https://kind.krx.co.kr/corpgeneral/corpList.do"
#         "?method=download"
#     )

#     df = pd.read_html(
#         url,
#         encoding="cp949"
#     )[0]

#     # 종목코드 6자리
#     df["종목코드"] = (
#         df["종목코드"]
#         .astype(str)
#         .str.zfill(6)
#     )

#     # KOSPI만
#     df = df[df["시장구분"] == "KOSPI"]
#     print(df["시장구분"].unique())
#     print(df.columns.tolist())

#     print(df.columns)
#     print(df.head())

#     # 우선주 제거
#     df = df[
#         ~df["회사명"].str.endswith("우", na=False)
#     ]

#     # 스팩 제거
#     df = df[
#         ~df["회사명"].str.contains("스팩", na=False)
#     ]

#     stocks = []

#     for _, row in df.iterrows():

#         stocks.append({
#             "ticker": row["종목코드"] + ".KS",
#             "name": row["회사명"]
#         })

#     return stocks