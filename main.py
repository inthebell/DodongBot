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

DODONG_GUILD_ID = 1517850860322029618
@bot.event
async def on_ready():
    print(f"{bot.user} 로그인 완료!")

    try:
        synced = await bot.tree.sync()

        guild = discord.Object(id=DODONG_GUILD_ID)
        guild_synced = await bot.tree.sync(guild=guild)

        print(f"글로벌 명령어 {len(synced)}개 동기화 완료!")
        print(f"도동마을 명령어 {len(guild_synced)}개 동기화 완료!")
    except Exception as e:
        print(e)

    print("도동봇 온라인!")


async def load_extensions():
    await bot.load_extension("cogs.ping")
    await bot.load_extension("cogs.help")
    await bot.load_extension("cogs.cooking")
    await bot.load_extension("cogs.alchemy")
    await bot.load_extension("cogs.donghyeop")
    await bot.load_extension("cogs.wiki")
    await bot.load_extension("cogs.level")
    await bot.load_extension("cogs.verify")
async def main():
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)


import asyncio
asyncio.run(main())
