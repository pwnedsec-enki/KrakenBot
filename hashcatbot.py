import aiohttp
import asyncio
import logging

class HashtopolisAPIError(Exception):
    pass

class HashtopolisManager:
    def __init__(self, server_url, username, password, max_retries=3, backoff_factor=1.0):
        self.server_url = server_url.rstrip('/')
        self.username = username
        self.password = password
        self.token = None
        self.session = None
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    async def login(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()

        login_url = f"{self.server_url}/api/login"
        data = {"user": self.username, "pass": self.password}

        for attempt in range(1, self.max_retries + 1):
            try:
                async with self.session.post(login_url, json=data) as resp:
                    if resp.status != 200:
                        logging.warning(f"Login attempt {attempt} failed with HTTP {resp.status}")
                        await self._sleep_backoff(attempt)
                        continue
                    json_resp = await resp.json()
                    if json_resp.get("success"):
                        self.token = json_resp.get("token")
                        logging.info("Logged in to Hashtopolis API successfully")
                        return True
                    else:
                        raise HashtopolisAPIError(f"Login failed: {json_resp.get('error')}")
            except Exception as e:
                logging.warning(f"Login attempt {attempt} exception: {e}")
                await self._sleep_backoff(attempt)

        raise HashtopolisAPIError("Exceeded max login retries")

    async def _sleep_backoff(self, attempt):
        delay = self.backoff_factor * (2 ** (attempt - 1))
        logging.info(f"Retrying after {delay:.1f} seconds...")
        await asyncio.sleep(delay)

    async def _request(self, method, endpoint, payload=None, params=None):
        if self.token is None:
            await self.login()

        url = f"{self.server_url}/api/{endpoint}"
        headers = {"Authorization": f"Bearer {self.token}"}

        for attempt in range(1, self.max_retries + 1):
            try:
                async with self.session.request(method, url, json=payload, params=params, headers=headers) as resp:
                    if resp.status == 401:
                        logging.info("Token expired or unauthorized, re-logging in")
                        await self.login()
                        continue

                    if resp.status != 200:
                        logging.warning(f"API {method} {endpoint} attempt {attempt} failed HTTP {resp.status}")
                        await self._sleep_backoff(attempt)
                        continue

                    json_resp = await resp.json()
                    if not json_resp.get("success", False):
                        logging.warning(f"API {method} {endpoint} returned error: {json_resp.get('error')}")
                    return json_resp

            except aiohttp.ClientError as e:
                logging.warning(f"API {method} {endpoint} attempt {attempt} exception: {e}")
                await self._sleep_backoff(attempt)

        raise HashtopolisAPIError(f"Failed API {method} {endpoint} after {self.max_retries} attempts")

    async def create_hashlist(self, name, algorithm):
        payload = {"name": name, "algorithm": algorithm}
        return await self._request("POST", "hashlist/new", payload)

    async def upload_hashes(self, hashlist_id, hashes):
        payload = {"hashlist_id": hashlist_id, "hashes": hashes}
        return await self._request("POST", "hashlist/upload", payload)

    async def create_task(self, name, hashlist_id, wordlist, rules=None):
        payload = {
            "name": name,
            "hashlist_id": hashlist_id,
            "wordlist": wordlist,
            "rules": rules or "",
        }
        return await self._request("POST", "task/new", payload)

    async def get_task_status(self, task_id):
        return await self._request("GET", f"task/status/{task_id}")

    async def get_cracked_hashes(self, task_id):
        return await self._request("GET", f"task/cracked/{task_id}")

    async def generate_setup_token(self):
        return await self._request("POST", "setup/generateAgentToken")

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None
            logging.info("Hashtopolis HTTP session closed")

