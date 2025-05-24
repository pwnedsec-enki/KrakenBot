import asyncio
import logging
import secrets
import functools
import os
import tempfile
from discord.ext import commands
from discord import File
from config import (
    HASHTOPOLIS_URL,
    HASHTOPOLIS_USER,
    HASHTOPOLIS_PASSWORD,
    TRUSTED_ROLE_NAME,
    SUPPORTED_ALGORITHMS,
    HASH_PATTERNS
)
from hashtopolis_manager import HashtopolisManager

DEFAULT_WORDLIST_ID = 1  # <-- Set this to a valid fileId for your default wordlist

class HashValidationError(Exception):
    pass

def validate_hash_input(algorithm, hash_value):
    if algorithm not in SUPPORTED_ALGORITHMS:
        raise HashValidationError("Unsupported algorithm.")
    if not HASH_PATTERNS[algorithm].match(hash_value):
        raise HashValidationError("Invalid hash format for that algorithm.")

class JobManager:
    def __init__(self):
        self.active_jobs = {}

    def has_active_job(self, user_id, hash_value):
        return (user_id, hash_value) in self.active_jobs

    def add_job(self, user_id, hash_value):
        self.active_jobs[(user_id, hash_value)] = {"status": "running"}

    def remove_job(self, user_id, hash_value):
        self.active_jobs.pop((user_id, hash_value), None)

def trusted_only():
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, ctx, *args, **kwargs):
            if TRUSTED_ROLE_NAME.lower() not in [role.name.lower() for role in ctx.author.roles]:
                await ctx.send("You are not authorized to use this command.")
                return
            return await func(self, ctx, *args, **kwargs)
        return wrapper
    return decorator

class HashcatBot(commands.Cog):
    def __init__(self, bot, job_manager):
        self.bot = bot
        self.job_manager = job_manager
        self.hashtopolis = HashtopolisManager(
            HASHTOPOLIS_URL, HASHTOPOLIS_USER, HASHTOPOLIS_PASSWORD
        )

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            await self.hashtopolis.login()
            logging.info("Logged in to Hashtopolis API successfully")
        except Exception as e:
            logging.error(f"Failed to login to Hashtopolis: {e}")

    def cog_unload(self):
        if self.hashtopolis:
            asyncio.create_task(self.hashtopolis.close())

    @commands.command(name="register_agent")
    @trusted_only()
    async def register_agent(self, ctx):
        voucher_code = secrets.token_hex(16)
        tmp_file_path = None
        setup_token = None
        try:
            resp = await self.hashtopolis.create_voucher(voucher_code)
            setup_token = resp.get("voucher")
            if not setup_token:
                raise Exception(f"Voucher creation failed: {resp}")

            base_dir = os.path.dirname(os.path.abspath(__file__))
            template_path = os.path.join(base_dir, "templates", "register_agent.txt")
            with open(template_path, "r") as f:
                instructions = f.read()
            safe_url = f"<{HASHTOPOLIS_URL}>"
            instructions = instructions.replace("{username}", ctx.author.name)
            instructions = instructions.replace("{server_url}", safe_url)
            instructions = instructions.replace("{agent_token}", setup_token)

            host_root = HASHTOPOLIS_URL.split('/api')[0]
            download_url = f"{host_root}/agents.php?download=4"

            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
            async with self.hashtopolis.session.get(download_url) as dl:
                if dl.status != 200:
                    raise Exception(f"Failed to download agent ZIP: HTTP {dl.status}")
                content = await dl.read()
                tmp_file.write(content)
                tmp_file.flush()
            tmp_file_path = tmp_file.name
            tmp_file.close()

            await ctx.author.send(instructions, file=File(tmp_file_path))
            await ctx.send("Agent onboarding instructions and agent ZIP sent via DM.")

        except FileNotFoundError as e:
            logging.error(f"Template file not found: {e}")
            await ctx.send("Template for agent registration is missing. Please contact an admin.")
        except Exception as e:
            logging.error(f"Agent registration failed: {e}")
            fallback = (
                f"Hi {ctx.author.name},\n\n"
                "We couldn't complete automatic onboarding.\n"
                "Please contact an admin for manual token creation.\n\n"
                f"Server URL: {HASHTOPOLIS_URL}\n"
                f"Setup Token: {setup_token if setup_token else 'N/A'}"
            )
            try:
                await ctx.author.send(fallback)
            except Exception:
                logging.error("Failed to send DM fallback instructions.")
            await ctx.send("Token generation failed. Sent fallback instructions via DM.")
        finally:
            if tmp_file_path and os.path.exists(tmp_file_path):
                try:
                    os.remove(tmp_file_path)
                except Exception as e:
                    logging.warning(f"Could not delete temp file {tmp_file_path}: {e}")

    @commands.command(name="hashcat")
    @trusted_only()
    async def hashcat(self, ctx, algorithm: str = None, hash_value: str = None, wordlist_id: int = None):
        """
        Submit a hash for cracking.
        Usage: !hashcat [algorithm] [hash_value] [wordlist_id (optional)]
        """
        if not algorithm or not hash_value:
            await ctx.send("Usage: !hashcat [algorithm] [hash_value] [wordlist_id (optional)]")
            return
        try:
            validate_hash_input(algorithm, hash_value)
        except HashValidationError as e:
            await ctx.send(str(e))
            return

        if self.job_manager.has_active_job(ctx.author.id, hash_value):
            await ctx.send("You already submitted this hash. Please wait for the current job to complete.")
            return

        hashTypeId = int(SUPPORTED_ALGORITHMS[algorithm])
        wordlist_id = int(wordlist_id) if wordlist_id else DEFAULT_WORDLIST_ID

        self.job_manager.add_job(ctx.author.id, hash_value)
        try:
            hashlist_name = f"{ctx.author.name}_{algorithm}_{hash_value[:8]}"
            hashlist_resp = await self.hashtopolis.create_hashlist(hashlist_name, hashTypeId, hash_value)
            hashlist_id = hashlist_resp.get("hashlistId") or hashlist_resp.get("id")
            if not hashlist_id:
                raise Exception("Failed to create hashlist.")

            task_name = f"Crack_{algorithm}_{hash_value[:8]}"
            task_resp = await self.hashtopolis.create_task(
                task_name=task_name,
                hashlist_id=hashlist_id,
                wordlist_id=wordlist_id,
                attack_cmd="-a 0 #HL# #WL#"
            )
            task_id = task_resp.get("taskId") or task_resp.get("id")
            if not task_id:
                raise Exception("Failed to create cracking task.")

            await ctx.send(
                f"Cracking task created! Task ID: {task_id}\n"
                f"Use `!task_status {task_id}` to check status."
            )
        except Exception as e:
            logging.error(f"Error during hash submission: {e}")
            await ctx.send(f"Failed to submit hash for cracking: {e}")
        finally:
            self.job_manager.remove_job(ctx.author.id, hash_value)

    @commands.command(name="tasks")
    @trusted_only()
    async def tasks(self, ctx):
        resp = await self.hashtopolis._request("GET", "ui/tasks")
        tasks = resp.get("tasks", []) or resp.get("tasks")
        if not tasks:
            await ctx.send("No tasks found.")
            return
        msg = ["**Tasks:**"]
        for t in tasks:
            task_id = t.get('taskId') or t.get('id')
            msg.append(f"ID: {task_id} | Name: {t.get('name')} | Status: {t.get('status')}")
        await ctx.send("\n".join(msg))

    @commands.command(name="task_status")
    @trusted_only()
    async def task_status(self, ctx, task_id: int = None):
        if not task_id:
            await ctx.send("Usage: !task_status <task_id>")
            return
        resp = await self.hashtopolis.get_task_status(task_id)
        status = resp.get("status")
        elapsed = resp.get("elapsedTime")
        progress = resp.get("progress")
        await ctx.send(f"Task {task_id} → Status: {status} | Elapsed: {elapsed} | Progress: {progress}")

    @commands.command(name="task_stop")
    @trusted_only()
    async def task_stop(self, ctx, task_id: int = None):
        if not task_id:
            await ctx.send("Usage: !task_stop <task_id>")
            return
        await self.hashtopolis._request("POST", "ui/helper/purgeTask", payload={"taskId": task_id})
        await ctx.send(f"Stop request sent for task {task_id}.")

    @commands.command(name="wordlists")
    @trusted_only()
    async def wordlists(self, ctx):
        try:
            wordlists = await self.hashtopolis.get_wordlists_v2()
            if not wordlists:
                await ctx.send("No wordlists found.")
                return
            msg = ["**Available Wordlists:**"]
            for wl in wordlists:
                wl_id = wl.get('fileId')
                wl_name = wl.get('filename')
                wl_lines = wl.get('lineCount', 'unknown')
                wl_size = wl.get('size', 'unknown')
                msg.append(f"ID: {wl_id} | Name: {wl_name} | Lines: {wl_lines} | Size: {wl_size}")
            await ctx.send("\n".join(msg))
        except Exception as e:
            await ctx.send(f"Failed to retrieve wordlists: {e}")

async def setup(bot):
    job_manager = JobManager()
    await bot.add_cog(HashcatBot(bot, job_manager))
