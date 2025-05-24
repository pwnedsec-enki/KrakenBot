import asyncio
import logging
import discord
from discord.ext import commands
from config import DISCORD_TOKEN

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    logging.info(f"Bot logged in as {bot.user}")

async def main():
    await bot.load_extension("hashcatbot")
    await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())