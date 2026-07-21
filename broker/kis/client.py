"""
KIS HTTP Client
"""


from typing import Any

import httpx

from config.settings import settings



class KisClient:


    def __init__(self):

        self.client = httpx.Client(

            base_url=settings.kis_base_url,

            timeout=10.0

        )



    def get(

        self,

        url: str,

        headers: dict | None = None,

        params: dict | None = None

    ) -> httpx.Response:


        response = self.client.get(

            url,

            headers=headers,

            params=params

        )


        response.raise_for_status()


        return response



    def post(

        self,

        url: str,

        headers: dict | None = None,

        json: dict[str, Any] | None = None

    ) -> httpx.Response:


        response = self.client.post(

            url,

            headers=headers,

            json=json

        )


        response.raise_for_status()


        return response



    def close(self):

        self.client.close()