from datetime import datetime, timedelta, timezone

import discord


USE_LOG_CHANNEL_ID = 1525343893883850833
MARKET_LOG_CHANNEL_ID = 1526164464544649296
KST = timezone(timedelta(hours=9))


async def send_use_log(
    bot,
    title: str,
    user: discord.abc.User,
    guild: discord.Guild,
    channel: discord.abc.GuildChannel,
    search_query: str | None = None
):
    log_channel = bot.get_channel(USE_LOG_CHANNEL_ID)

    if log_channel is None:
        try:
            log_channel = await bot.fetch_channel(USE_LOG_CHANNEL_ID)
        except Exception as e:
            print(f"사용 로그 채널을 찾지 못했습니다: {e}")
            return

    now = datetime.now(KST)

    embed = discord.Embed(
        title=title,
        color=discord.Color.blurple(),
        timestamp=now
    )

    if search_query:
        embed.add_field(
            name="검색어",
            value=search_query,
            inline=False
        )

    embed.add_field(
        name="사용자",
        value=str(user),
        inline=False
    )

    embed.add_field(
        name="ID",
        value=f"`{user.id}`",
        inline=False
    )

    embed.add_field(
        name="서버",
        value=guild.name,
        inline=False
    )

    embed.add_field(
        name="채널",
        value=channel.mention,
        inline=False
    )

    embed.set_footer(
        text="DodongBot Usage Log"
    )

    await log_channel.send(embed=embed)

async def send_market_log(
    bot,
    user: discord.abc.User,
    guild: discord.Guild,
    channel: discord.abc.GuildChannel,
    keyword: str,
    result: str,
):
    log_channel = bot.get_channel(MARKET_LOG_CHANNEL_ID)

    if log_channel is None:
        try:
            log_channel = await bot.fetch_channel(MARKET_LOG_CHANNEL_ID)
        except Exception as e:
            print(f"시세 로그 채널을 찾지 못했습니다: {e}")
            return

    now = datetime.now(KST)

    embed = discord.Embed(
        title="💰 시세 조회",
        color=discord.Color.gold(),
        timestamp=now
    )

    embed.add_field(
        name="검색어",
        value=keyword,
        inline=False
    )

    embed.add_field(
        name="조회 결과",
        value=result,
        inline=False
    )

    embed.add_field(
        name="사용자",
        value=str(user),
        inline=False
    )

    embed.add_field(
        name="ID",
        value=f"`{user.id}`",
        inline=False
    )

    embed.add_field(
        name="서버",
        value=guild.name,
        inline=False
    )

    embed.add_field(
        name="채널",
        value=channel.mention,
        inline=False
    )

    embed.set_footer(
        text="DodongBot Market Log"
    )

    await log_channel.send(embed=embed)