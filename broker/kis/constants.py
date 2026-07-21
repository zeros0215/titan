"""
Korea Investment OpenAPI Constants

한국투자증권 OpenAPI에서 사용하는
URL, Header, TR ID 등을 관리한다.
"""

# ==========================================================
# OAuth
# ==========================================================

TOKEN_URL = "/oauth2/tokenP"

HASHKEY_URL = "/uapi/hashkey"

GRANT_TYPE = "client_credentials"


# ==========================================================
# Header
# ==========================================================

CONTENT_TYPE = "application/json"

AUTHORIZATION = "authorization"

APP_KEY = "appkey"

APP_SECRET = "appsecret"

TR_ID = "tr_id"


# ==========================================================
# Market
# ==========================================================

DAILY_PRICE_URL = (
    "/uapi/domestic-stock/v1/quotations/"
    "inquire-daily-price"
)

CURRENT_PRICE_URL = (
    "/uapi/domestic-stock/v1/quotations/"
    "inquire-price"
)


# ==========================================================
# WebSocket
# ==========================================================

REAL_WS_URL = (
    "ws://ops.koreainvestment.com:21000"
)

VIRTUAL_WS_URL = (
    "ws://ops.koreainvestment.com:31000"
)


# ==========================================================
# TR ID
# ==========================================================

TR_DAILY_PRICE = "FHKST01010400"

TR_CURRENT_PRICE = "FHKST01010100"

# ======================================================
# Market
# ======================================================

MARKET_KOSPI = "J"

PERIOD_DAY = "D"

ADJUSTED_PRICE = "1"



"""
KIS Market API
"""

DAILY_PRICE_URL = (
    "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
)

TR_ID_DAILY_PRICE = "FHKST03010100"

MARKET_DIVISION = "J"

PERIOD_DAY = "D"

ORIGINAL_PRICE = "1"