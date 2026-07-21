"""
Application Settings
"""

from dataclasses import dataclass

from dotenv import load_dotenv

import os


load_dotenv()


@dataclass(slots=True, frozen=True)
class Settings:

    env: str

    market_provider: str

    log_level: str

    kis_app_key: str

    kis_app_secret: str

    kis_base_url: str

    kis_account: str

    kis_mode: str

    
settings = Settings(

    env=os.getenv("ENV", "DEV"),

    market_provider=os.getenv(

        "MARKET_PROVIDER",

        "MOCK"

    ),

    log_level=os.getenv(

        "LOG_LEVEL",

        "INFO"

    ),

    kis_app_key=os.getenv(

        "KIS_APP_KEY",

        ""

    ),

    kis_app_secret=os.getenv(

        "KIS_APP_SECRET",

        ""

    ),

    kis_base_url=os.getenv(

        "KIS_BASE_URL",

        ""

    ),

    kis_account=os.getenv(

        "KIS_ACCOUNT",

        ""

    ),

    kis_mode=os.getenv(
    "KIS_MODE",
    "VIRTUAL"
),

)