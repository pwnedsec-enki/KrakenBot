import aiohttp
import asyncio
import logging

class HashtopolisAPIError(Exception):
    """Raised when an API call to Hashtopolis fails irrecoverably."""
    pass

class HashtopolisManager:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        max_retries: int = 3,
        backoff_factor: float = 1.0
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.token = None
        self.session: aiohttp.ClientSession | None = None
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    async def login(self) -> None:
        if self.session is None:
            self.session = aiohttp.ClientSession()
        auth_url = f"{self.base_url}/auth/token"
        for attempt in range(1, self.max_retries + 1):
            try:
                async with self.session.post(
                    auth_url,
                    auth=aiohttp.BasicAuth(self.username, self.password)
                ) as resp:
                    if resp.status < 200 or resp.status >= 300:
                        logging.warning(
                            f"Login attempt {attempt} failed with HTTP {resp.status}"
                        )
                        await self._sleep_backoff(attempt)
                        continue
                    data = await resp.json()
                    if "token" not in data:
                        logging.warning(f"Login response missing token: {data}")
                        await self._sleep_backoff(attempt)
                        continue
                    self.token = data["token"]
                    logging.info("Hashtopolis API v2 token acquired")
                    return
            except Exception as e:
                logging.warning(f"Login attempt {attempt} exception: {e}")
                await self._sleep_backoff(attempt)
        raise HashtopolisAPIError("Exceeded max login retries")

    async def _sleep_backoff(self, attempt: int) -> None:
        delay = self.backoff_factor * (2 ** (attempt - 1))
        await asyncio.sleep(delay)

    async def _request(
        self,
        method: str,
        endpoint: str,
        payload: dict | None = None,
        params: dict | None = None
    ) -> dict:
        if self.token is None:
            await self.login()
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {"Authorization": f"Bearer {self.token}"}
        for attempt in range(1, self.max_retries + 1):
            try:
                async with self.session.request(
                    method, url, json=payload, params=params, headers=headers
                ) as resp:
                    if resp.status == 401:
                        logging.info(
                            "Token expired or unauthorized, re-authenticating"
                        )
                        self.token = None
                        await self.login()
                        continue
                    if resp.status >= 400:
                        text = await resp.text()
                        logging.warning(
                            f"API {method} {endpoint} failed HTTP {resp.status}: {text}"
                        )
                        await self._sleep_backoff(attempt)
                        continue
                    return await resp.json()
            except aiohttp.ClientError as e:
                logging.warning(f"API {method} {endpoint} exception: {e}")
                await self._sleep_backoff(attempt)
        raise HashtopolisAPIError(
            f"Failed API {method} {endpoint} after {self.max_retries} attempts"
        )

    async def close(self) -> None:
        if self.session:
            await self.session.close()
            self.session = None
            logging.info("Hashtopolis HTTP session closed")

    # --- Helper methods for UI endpoints ---
    async def create_voucher(self, voucher_code: str) -> dict:
        return await self._request("POST", "ui/vouchers", payload={"voucher": voucher_code})

    async def create_hashlist(
        self,
        name: str,
        hashTypeId: int,
        hash_value: str,
        accessGroupId: int = 1
    ) -> dict:
        payload = {
            "name": name,
            "hashTypeId": hashTypeId,
            "sourceType": "paste",
            "sourceData": hash_value,
            "format": 1,
            "hashCount": 1,
            "isSecret": False,
            "isHexSalt": False,
            "isSalted": False,
            "accessGroupId": accessGroupId,
            "notes": "",
            "useBrain": False,
            "brainFeatures": 0,
            "isArchived": False
        }
        return await self._request("POST", "ui/hashlists", payload=payload)

    async def create_task(
        self,
        task_name: str,
        hashlist_id: int,
        wordlist_id: int,
        attack_cmd: str = "-a 0 #HL# #WL#"
    ) -> dict:
        # These values are based on successful curl troubleshooting
        payload = {
            "taskName": task_name,
            "hashlistId": hashlist_id,
            "files": [wordlist_id],
            "attackCmd": attack_cmd,
            "chunkTime": 600,
            "statusTimer": 60,
            "priority": 1,
            "maxAgents": 0,
            "isSmall": False,
            "isCpuTask": False,
            "useNewBench": False,
            "skipKeyspace": 0,
            "crackerBinaryId": 1,
            "crackerBinaryTypeId": 1,
            "isArchived": False,
            "notes": "",
            "staticChunks": 0,
            "chunkSize": 0,
            "forcePipe": False,
            "preprocessorId": 0,
            "preprocessorCommand": ""
        }
        return await self._request("POST", "ui/tasks", payload=payload)

    async def get_task_status(self, task_id: int) -> dict:
        return await self._request("GET", f"ui/tasks/{task_id}")

    async def get_cracked_hashes(self, task_id: int) -> dict:
        return await self._request("GET", f"ui/tasks/{task_id}/cracked")

    async def get_wordlists_v2(self) -> list:
        if self.token is None:
            await self.login()
        url = f"{self.base_url}/ui/files"
        headers = {"Authorization": f"Bearer {self.token}"}
        if self.session is None:
            self.session = aiohttp.ClientSession()
        async with self.session.get(url, headers=headers) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise HashtopolisAPIError(
                    f"API v2 file list failed: HTTP {resp.status}: {text}"
                )
            data = await resp.json()
            files = data.get("values", [])
            wordlists = [f for f in files if f.get("fileType") == 0]
            return wordlists
