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

DM_LOG_CHANNEL_ID = 1525343943867498668


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if isinstance(message.channel, discord.DMChannel):
        log_channel = bot.get_channel(DM_LOG_CHANNEL_ID)

        if log_channel is None:
            try:
                log_channel = await bot.fetch_channel(DM_LOG_CHANNEL_ID)
            except Exception as e:
                print(f"문의 로그 채널을 찾지 못했습니다: {e}")
                return

        embed = discord.Embed(
            title="📩 새로운 DM 문의",
            description=message.content or "(내용 없음)",
            color=discord.Color.blurple()
        )

        embed.add_field(
            name="보낸 사람",
            value=f"{message.author} (`{message.author.id}`)",
            inline=False
        )

        if message.attachments:
            attachment_links = "\n".join(
                attachment.url for attachment in message.attachments
            )
            embed.add_field(
                name="첨부파일",
                value=attachment_links,
                inline=False
            )

        embed.set_thumbnail(url=message.author.display_avatar.url)

        await log_channel.send(embed=embed)

    await bot.process_commands(message)

async def load_extensions():
    await bot.load_extension("cogs.ping")
    await bot.load_extension("cogs.help")
    await bot.load_extension("cogs.cooking")
    await bot.load_extension("cogs.alchemy")
    await bot.load_extension("cogs.donghyeop")
    await bot.load_extension("cogs.wiki")
    await bot.load_extension("cogs.level")
    await bot.load_extension("cogs.verify")
    await bot.load_extension("cogs.serverlist")
async def main():
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)


import asyncio
asyncio.run(main())
