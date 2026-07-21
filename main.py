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
OWNER_ID = 478834154595811328

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

        thread_name = f"📩 {message.author.name}님의 문의 ({message.author.id})"
        inquiry_thread = None

        for thread in log_channel.threads:
            if thread.name == thread_name:
                inquiry_thread = thread
                break

        if inquiry_thread is None:
            try:
                async for thread in log_channel.archived_threads(limit=100):
                    if thread.name == thread_name:
                        inquiry_thread = thread
                        break
            except Exception as e:
                print(f"보관된 문의 스레드 검색 오류: {e}")

        if inquiry_thread is None:
            starter_embed = discord.Embed(
                title="📩 새 문의 사용자",
                description=(
                    f"**사용자:** {message.author}\n"
                    f"**사용자 ID:** `{message.author.id}`"
                ),
                color=discord.Color.blurple(),
                timestamp=discord.utils.utcnow()
            )

            starter_embed.set_thumbnail(
                url=message.author.display_avatar.url
            )

            starter_embed.set_footer(
                text="DodongBot Support"
            )

            starter_message = await log_channel.send(
                embed=starter_embed
            )

            inquiry_thread = await starter_message.create_thread(
                name=thread_name,
                auto_archive_duration=10080
            )

        elif inquiry_thread.archived:
            try:
                await inquiry_thread.edit(archived=False)
            except Exception as e:
                print(f"문의 스레드 다시 열기 오류: {e}")

        await inquiry_thread.send(
            f"<@{OWNER_ID}> 🔔 **새로운 문의가 도착했습니다.**",
            allowed_mentions=discord.AllowedMentions(
                users=True,
                roles=False,
                everyone=False
            )
        )

        inquiry_embed = discord.Embed(
            title="📩 사용자 문의",
            description=message.content or "(내용 없음)",
            color=discord.Color.blurple(),
            timestamp=message.created_at
        )

        inquiry_embed.set_author(
            name=str(message.author),
            icon_url=message.author.display_avatar.url
        )

        inquiry_embed.add_field(
            name="사용자 ID",
            value=f"`{message.author.id}`",
            inline=False
        )

        if message.attachments:
            attachment_links = "\n".join(
                attachment.url for attachment in message.attachments
            )

            inquiry_embed.add_field(
                name="첨부파일",
                value=attachment_links,
                inline=False
            )

            first_attachment = message.attachments[0]

            if (
                first_attachment.content_type
                and first_attachment.content_type.startswith("image/")
            ):
                inquiry_embed.set_image(
                    url=first_attachment.url
                )

        inquiry_embed.set_footer(
            text="DodongBot Support"
        )

        await inquiry_thread.send(embed=inquiry_embed)

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
    await bot.load_extension("cogs.dmreply")
    await bot.load_extension("cogs.timer")
    await bot.load_extension("cogs.market")
    await bot.load_extension("cogs.tax")
    await bot.load_extension("cogs.game_rules")
async def main():
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)


import asyncio
asyncio.run(main())
