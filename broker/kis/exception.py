"""
KIS Exceptions
"""


class KisException(Exception):
    """KIS Base Exception"""


class KisApiException(KisException):

    def __init__(

        self,

        code: str,

        message: str

    ):

        self.code = code

        self.message = message

        super().__init__(

            f"[{code}] {message}"

        )


class KisAuthenticationException(

    KisApiException

):
    """OAuth Error"""


class KisMarketException(

    KisApiException

):
    """Market API Error"""