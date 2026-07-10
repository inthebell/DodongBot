import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


@bot.event
async def on_ready():
    print(f"{bot.user} 로그인 완료!")

    try:
        synced = await bot.tree.sync()
        print(f"슬래시 명령어 {len(synced)}개 동기화 완료!")
    except Exception as e:
        print(e)

    print("도동봇 온라인!")


async def load_extensions():
    await bot.load_extension("cogs.ping")
    await bot.load_extension("cogs.help")
    await bot.load_extension("cogs.cooking")
    await bot.load_extension("cogs.alchemy")
    await bot.load_extension("cogs.level")
    await bot.load_extension("cogs.verify")
async def main():
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)


import asyncio
asyncio.run(main())
