import discord
from discord.ext import commands
import logging
import sys
from config import DISCORD_TOKEN
from hashcatbot import HashcatBot, JobManager  # Import the cog and JobManager

logging.basicConfig(level=logging.INFO)

INTENTS = discord.Intents.default()
INTENTS.messages = True
INTENTS.message_content = True

bot = commands.Bot(command_prefix="!", intents=INTENTS)

# Create the shared job manager instance
job_manager = JobManager()

# Instantiate the HashcatBot cog with the bot and job manager
hashcat_bot = HashcatBot(bot, job_manager)
bot.add_cog(hashcat_bot)

@bot.event
async def on_ready():
    logging.info(f"Bot logged in as {bot.user}")

@bot.event
async def on_close():
    # Graceful shutdown: close Hashtopolis session if needed
    await hashcat_bot.hashtopolis.close()

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logging.error("DISCORD_BOT_TOKEN is not set. Exiting.")
        sys.exit(1)
    bot.run(DISCORD_TOKEN)

