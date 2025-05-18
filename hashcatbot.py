import asyncio
import logging
from discord.ext import commands
from config import (
    SUPPORTED_ALGORITHMS,
    HASH_PATTERNS,
    TRUSTED_ROLE_NAME,
    HASHTOPOLIS_URL,
    HASHTOPOLIS_USER,
    HASHTOPOLIS_PASSWORD,
)
from hashtopolis_manager import HashtopolisManager
from main_bot import JobManager, trusted_only, validate_hash_input, HashValidationError  # Import shared utilities

class JobProcessor:
    def __init__(self, bot, job_manager, hashtopolis, concurrency=2):
        self.bot = bot
        self.job_manager = job_manager
        self.hashtopolis = hashtopolis
        self.queue = asyncio.Queue()
        self.semaphore = asyncio.Semaphore(concurrency)
        self.running = False

    async def start(self):
        if not self.running:
            self.running = True
            asyncio.create_task(self.worker())

    async def enqueue_job(self, ctx, algorithm, hash_value):
        await self.queue.put((ctx, algorithm, hash_value))

    async def worker(self):
        while self.running:
            ctx, algorithm, hash_value = await self.queue.get()
            async with self.semaphore:
                try:
                    await self.process_job(ctx, algorithm, hash_value)
                except Exception as e:
                    logging.error(f"Error processing job for user {ctx.author.id}: {e}")
                    await ctx.send(f"Error processing job: {e}")
                finally:
                    self.queue.task_done()

    async def process_job(self, ctx, algorithm, hash_value):
        if self.job_manager.has_active_job(ctx.author.id, hash_value):
            await ctx.send("You already have this hash cracking in progress. Please wait.")
            return

        self.job_manager.add_job(ctx.author.id, hash_value)
        await ctx.send(f"Starting cracking job for your hash with algorithm {algorithm}...")

        # Step 1: Create hashlist
        hashlist_resp = await self.hashtopolis.create_hashlist(
            f"discord-{ctx.author.id}-{algorithm}", SUPPORTED_ALGORITHMS[algorithm]
        )
        if not hashlist_resp or not hashlist_resp.get("success"):
            await ctx.send("Failed to create hashlist.")
            self.job_manager.remove_job(ctx.author.id, hash_value)
            return
        hashlist_id = hashlist_resp.get("hashlist_id")

        # Step 2: Upload hash
        upload_resp = await self.hashtopolis.upload_hashes(hashlist_id, [hash_value])
        if not upload_resp or not upload_resp.get("success"):
            await ctx.send("Failed to upload hash.")
            self.job_manager.remove_job(ctx.author.id, hash_value)
            return

        # Step 3: Create task
        task_resp = await self.hashtopolis.create_task(
            f"discord-{ctx.author.id}-{algorithm}-task", hashlist_id, "rockyou.txt"
        )
        if not task_resp or not task_resp.get("success"):
            await ctx.send("Failed to create cracking task.")
            self.job_manager.remove_job(ctx.author.id, hash_value)
            return
        task_id = task_resp.get("task_id")

        await ctx.send(f"Cracking task created with ID {task_id}. This may take some time.")

        # Step 4: Poll status and wait for completion (poll every 10s up to 1 hour)
        for _ in range(360):
            await asyncio.sleep(10)
            status_resp = await self.hashtopolis.get_task_status(task_id)
            if not status_resp or not status_resp.get("success"):
                continue
            status = status_resp.get("status")
            if status == "done":
                cracked = await self.hashtopolis.get_cracked_hashes(task_id)
                if cracked and cracked.get("success") and cracked.get("hashes"):
                    password = cracked["hashes"][0].get("password", None)
                    await ctx.send(f"Hash cracked! Password: `{password}`")
                else:
                    await ctx.send("Task completed but password was not found.")
                break
            elif status == "failed":
                await ctx.send("Cracking task failed.")
                break
        else:
            await ctx.send("Cracking task timed out after 1 hour.")

        self.job_manager.remove_job(ctx.author.id, hash_value)


class HashcatBot(commands.Cog):
    def __init__(self, bot, job_manager):
        self.bot = bot
        self.job_manager = job_manager
        self.hashtopolis = HashtopolisManager(
            HASHTOPOLIS_URL, HASHTOPOLIS_USER, HASHTOPOLIS_PASSWORD
        )
        self.job_processor = JobProcessor(bot, job_manager, self.hashtopolis)
        self.bot.loop.create_task(self.hashtopolis.login())
        self.bot.loop.create_task(self.job_processor.start())

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"Bot logged in as {self.bot.user}")

    @commands.command(name="register_agent")
    @trusted_only()
    async def register_agent(self, ctx):
        try:
            with open("templates/register_agent.txt", "r") as f:
                instructions = f.read()
            # Replace placeholders dynamically
            instructions = instructions.replace("{username}", ctx.author.name)
            instructions = instructions.replace("{server_url}", HASHTOPOLIS_URL)
            instructions = instructions.replace("{agent_token}", self.hashtopolis.password)
        except Exception as e:
            logging.error(f"Failed to load registration instructions: {e}")
            fallback = (
                f"Hi {ctx.author.name},\n\n"
                "You're now approved to contribute a cracking agent.\n\n"
                "1. Install requirements:\n"
                "   pip install -r requirements.txt\n\n"
                "2. Download the agent:\n"
                "   https://github.com/s3inlc/hashtopolis/tree/master/agent\n\n"
                f"3. Run the agent:\n"
                f"   python agent.py --server {HASHTOPOLIS_URL} --token {self.hashtopolis.password}\n\n"
                "Let an admin know once your agent appears in Hashtopolis so it can be activated."
            )
            await ctx.author.send(fallback)
            await ctx.send("Template file not found. Sent fallback instructions via DM.")
            return

        await ctx.author.send(instructions)
        await ctx.send("Registration instructions sent via DM.")

    @commands.command(name="hashcat")
    @trusted_only()
    async def hashcat(self, ctx, algorithm: str = None, hash_value: str = None):
        if not algorithm or not hash_value:
            await ctx.send("Usage: !hashcat [algorithm] [hash_value]")
            return

        try:
            validate_hash_input(algorithm, hash_value)
        except HashValidationError as e:
            await ctx.send(str(e))
            return

        await self.job_processor.enqueue_job(ctx, algorithm, hash_value)
        await ctx.send("Your cracking job has been queued. You will be notified when it completes.")

