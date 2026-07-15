import asyncio
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.log_manager import send_use_log

from utils.channel_manager import (
    get_channel_id,
    get_setting_enabled,
    remove_channel_id,
    set_channel_id,
    set_setting_enabled,
)


RUNE_PRICE_RANGE = {
    "룬 ㅣ 화염저항": (180, 270),
    "룬 ㅣ 호흡": (207, 311),
    "룬 ㅣ 신속": (228, 342),
    "룬 ㅣ 성급": (402, 603),
    "룬 ㅣ 힘": (405, 608),
}


ALCHEMY_PATTERN = re.compile(
    r"\[(.*?)\]\s*\|\s*(\d+)\s*→\s*(\d+)"
)


ALCHEMY_ALERT_BEFORE_TEXT = (
    "🔔 **만들어둔 연금술품 파셨나요?**\n\n"
    "변동상점 갱신까지 10분 남았습니다!"
)

ALCHEMY_ALERT_UPDATED_TEXT = (
    "🧪 **연금 변동상점이 갱신되었습니다!**\n\n"
    "새로운 시세를 확인해보세요."
)

ALCHEMY_ALERT_PREFIXES = (
    "🔔 **만들어둔 연금술품 파셨나요?**",
    "🧪 **연금 변동상점이 갱신되었습니다!**",
)


def get_status(price: int, low: int, high: int) -> str:
    mid = (low + high) / 2
    high_point = low + (high - low) * 0.9

    if price >= high_point:
        return "고점"

    if price >= mid:
        return "추천"

    return "저점"


def contains_valid_alchemy_data(text: str) -> bool:
    matches = ALCHEMY_PATTERN.findall(text)

    if not matches:
        return False

    for raw_name, _, _ in matches:
        name = raw_name.strip()

        if name in RUNE_PRICE_RANGE:
            return True

    return False


def parse_alchemy(text: str) -> dict:
    results = {
        "고점": [],
        "추천": [],
    }

    for raw_name, _, current_price in ALCHEMY_PATTERN.findall(text):
        name = raw_name.strip()
        price_range = RUNE_PRICE_RANGE.get(name)

        if price_range is None:
            continue

        price = int(current_price)
        low, high = price_range
        status = get_status(price, low, high)

        if status == "저점":
            continue

        results[status].append(
            (name, price, low, high)
        )

    return results


def build_result_text(
    results: dict,
    updater_name: str,
    time_text: str,
) -> str:
    parts = ["🧪 **연금 변동상점**"]

    for status, title in [
        ("고점", "🔥 고점"),
        ("추천", "⭐ 추천"),
    ]:
        if status == "추천":
            parts.append("\n━━━━━━━━━━━━━━")

        parts.append(f"\n{title}")

        items = results.get(status, [])

        if not items:
            parts.append("없음")
            continue

        for name, price, low, high in items:
            parts.append(
                f"🧪 **{name}** - {price}원 "
                f"({low}~{high}원)"
            )

    parts.append("\n━━━━━━━━━━━━━━")
    parts.append(
        "\n※ 중간값 이하의 룬은 표시되지 않습니다."
    )
    parts.append(
        "※ 추천은 변동 시세의 중간값 이상, "
        "고점은 상위 10% 구간을 기준으로 선정됩니다."
    )

    parts.append("")
    parts.append(f"> 업데이트 : {updater_name} / {time_text}")

    return "\n".join(parts)


class Alchemy(commands.Cog):
    alchemy_group = app_commands.Group(
        name="연금",
        description="연금 변동상점 기능입니다.",
    )

    channel_group = app_commands.Group(
        name="변동채널",
        description="연금 변동상점 채널을 관리합니다.",
        parent=alchemy_group,
    )

    alert_group = app_commands.Group(
        name="알림",
        description="연금 변동상점 갱신 알림을 관리합니다.",
        parent=alchemy_group,
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_locks: dict[int, asyncio.Lock] = {}
        self.last_alchemy_alert_key: str | None = None
        self.alchemy_alert_task.start()

    def cog_unload(self) -> None:
        self.alchemy_alert_task.cancel()

    def get_guild_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self.update_locks:
            self.update_locks[guild_id] = asyncio.Lock()

        return self.update_locks[guild_id]

    @channel_group.command(
        name="설정",
        description="현재 채널을 연금 변동상점 채널로 설정합니다.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ 서버 안에서만 사용할 수 있는 명령어입니다.",
                ephemeral=True,
            )
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ 일반 텍스트 채널에서 실행해주세요.",
                ephemeral=True,
            )
            return

        bot_member = interaction.guild.me

        if bot_member is None:
            await interaction.response.send_message(
                "❌ 도동봇의 서버 권한을 확인할 수 없습니다.",
                ephemeral=True,
            )
            return

        permissions = interaction.channel.permissions_for(bot_member)
        missing_permissions = []

        if not permissions.view_channel:
            missing_permissions.append("채널 보기")

        if not permissions.send_messages:
            missing_permissions.append("메시지 보내기")

        if not permissions.read_message_history:
            missing_permissions.append("메시지 기록 보기")

        if not permissions.manage_messages:
            missing_permissions.append("메시지 관리")

        if missing_permissions:
            permission_text = "\n".join(
                f"• {permission}"
                for permission in missing_permissions
            )

            await interaction.response.send_message(
                "❌ 도동봇에게 필요한 채널 권한이 부족합니다.\n\n"
                f"{permission_text}\n\n"
                "권한을 허용한 뒤 다시 설정해주세요.",
                ephemeral=True,
            )
            return

        set_channel_id(
            interaction.guild.id,
            "alchemy",
            interaction.channel.id,
        )

        await interaction.response.send_message(
            "✅ 연금 변동상점 채널을 설정했습니다.\n\n"
            f"설정된 채널: {interaction.channel.mention}\n\n"
            "이제 동글랜드의 연금 변동상점 내용을 "
            "이 채널에 그대로 붙여넣으면 자동으로 분석됩니다.",
            ephemeral=True,
        )

    @channel_group.command(
        name="확인",
        description="현재 설정된 연금 변동상점 채널을 확인합니다.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def check_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ 서버 안에서만 사용할 수 있는 명령어입니다.",
                ephemeral=True,
            )
            return

        channel_id = get_channel_id(
            interaction.guild.id,
            "alchemy",
        )

        if channel_id is None:
            await interaction.response.send_message(
                "❌ 현재 설정된 연금 변동상점 채널이 없습니다.\n\n"
                "원하는 채널에서 `/연금 변동채널 설정`을 "
                "사용해주세요.",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(channel_id)

        if channel is None:
            await interaction.response.send_message(
                "⚠️ 설정된 채널을 찾을 수 없습니다.\n\n"
                "채널이 삭제되었을 수 있으므로 "
                "다시 설정해주세요.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "🧪 현재 연금 변동상점 채널\n\n"
            f"{channel.mention}",
            ephemeral=True,
        )

    @channel_group.command(
        name="해제",
        description="연금 변동상점 채널 설정을 해제합니다.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ 서버 안에서만 사용할 수 있는 명령어입니다.",
                ephemeral=True,
            )
            return

        removed = remove_channel_id(
            interaction.guild.id,
            "alchemy",
        )

        if not removed:
            await interaction.response.send_message(
                "❌ 현재 설정된 연금 변동상점 채널이 없습니다.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "✅ 연금 변동상점 채널 설정을 해제했습니다.",
            ephemeral=True,
        )

    @alert_group.command(
        name="켜기",
        description="연금 변동상점 갱신 알림을 켭니다.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def enable_alert(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ 서버 안에서만 사용할 수 있는 명령어입니다.",
                ephemeral=True,
            )
            return

        channel_id = get_channel_id(
            interaction.guild.id,
            "alchemy",
        )

        if channel_id is None:
            await interaction.response.send_message(
                "❌ 먼저 `/연금 변동채널 설정`으로 "
                "연금 변동상점 채널을 설정해주세요.",
                ephemeral=True,
            )
            return

        set_setting_enabled(
            interaction.guild.id,
            "alchemy_alert",
            True,
        )

        await interaction.response.send_message(
            "✅ 연금 변동상점 갱신 알림을 켰습니다.\n\n"
            "갱신 10분 전과 갱신 정각에 "
            "설정된 연금 변동상점 채널로 알림을 보냅니다.",
            ephemeral=True,
        )

    @alert_group.command(
        name="끄기",
        description="연금 변동상점 갱신 알림을 끕니다.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def disable_alert(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ 서버 안에서만 사용할 수 있는 명령어입니다.",
                ephemeral=True,
            )
            return

        set_setting_enabled(
            interaction.guild.id,
            "alchemy_alert",
            False,
        )

        channel = await self.get_alchemy_channel(interaction.guild)

        if channel is not None:
            await self.delete_alchemy_alerts(channel)

        await interaction.response.send_message(
            "✅ 연금 변동상점 갱신 알림을 껐습니다.",
            ephemeral=True,
        )

    @alert_group.command(
        name="확인",
        description="연금 변동상점 갱신 알림 상태를 확인합니다.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def check_alert(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ 서버 안에서만 사용할 수 있는 명령어입니다.",
                ephemeral=True,
            )
            return

        enabled = get_setting_enabled(
            interaction.guild.id,
            "alchemy_alert",
        )

        status_text = "켜짐" if enabled else "꺼짐"

        await interaction.response.send_message(
            "🧪 연금 변동상점 갱신 알림\n\n"
            f"현재 상태: **{status_text}**",
            ephemeral=True,
        )

    async def get_alchemy_channel(
        self,
        guild: discord.Guild,
    ) -> discord.TextChannel | None:
        channel_id = get_channel_id(guild.id, "alchemy")

        if channel_id is None:
            return None

        channel = guild.get_channel(channel_id)

        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                return None

        if not isinstance(channel, discord.TextChannel):
            return None

        return channel

    async def delete_alchemy_alerts(
        self,
        channel: discord.TextChannel,
    ) -> None:
        if self.bot.user is None:
            return

        try:
            async for previous_message in channel.history(limit=50):
                if previous_message.author.id != self.bot.user.id:
                    continue

                if not previous_message.content.startswith(
                    ALCHEMY_ALERT_PREFIXES
                ):
                    continue

                try:
                    await previous_message.delete()
                except (discord.Forbidden, discord.NotFound):
                    pass
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def send_alchemy_alert(
        self,
        channel: discord.TextChannel,
        content: str,
    ) -> None:
        await self.delete_alchemy_alerts(channel)

        try:
            await channel.send(content)
        except (discord.Forbidden, discord.HTTPException):
            pass

    @tasks.loop(seconds=30)
    async def alchemy_alert_task(self) -> None:
        now = datetime.now(ZoneInfo("Asia/Seoul"))

        alert_kind: str | None = None
        alert_text: str | None = None

        if now.minute == 50 and now.hour % 3 == 2:
            alert_kind = "before"
            alert_text = ALCHEMY_ALERT_BEFORE_TEXT
        elif now.minute == 0 and now.hour % 3 == 0:
            alert_kind = "updated"
            alert_text = ALCHEMY_ALERT_UPDATED_TEXT

        if alert_kind is None or alert_text is None:
            return

        alert_key = now.strftime(f"%Y-%m-%d-%H-{alert_kind}")

        if self.last_alchemy_alert_key == alert_key:
            return

        self.last_alchemy_alert_key = alert_key

        for guild in self.bot.guilds:
            if not get_setting_enabled(guild.id, "alchemy_alert"):
                continue

            channel = await self.get_alchemy_channel(guild)

            if channel is None:
                continue

            await self.send_alchemy_alert(channel, alert_text)

    @alchemy_alert_task.before_loop
    async def before_alchemy_alert_task(self) -> None:
        await self.bot.wait_until_ready()

    async def send_invalid_message_dm(
        self,
        member: discord.Member,
        channel: discord.TextChannel,
    ) -> None:
        try:
            await member.send(
                "❌ 연금 변동상점 채널에는 "
                "변동시세 내용만 입력할 수 있습니다.\n\n"
                f"잘못 입력한 메시지는 {channel.mention}에서 "
                "자동으로 삭제되었습니다."
            )
        except discord.Forbidden:
            pass

    async def delete_previous_results(
        self,
        channel: discord.TextChannel,
    ) -> None:
        if self.bot.user is None:
            return

        async for previous_message in channel.history(limit=50):
            if previous_message.author.id != self.bot.user.id:
                continue

            if not previous_message.content.startswith(
                "🧪 **연금 변동상점**"
            ):
                continue

            try:
                await previous_message.delete()
            except (discord.Forbidden, discord.NotFound):
                pass

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message,
    ) -> None:
        if message.author.bot:
            return

        if message.guild is None:
            return

        if not isinstance(message.channel, discord.TextChannel):
            return

        configured_channel_id = get_channel_id(
            message.guild.id,
            "alchemy",
        )

        if configured_channel_id is None:
            return

        if message.channel.id != configured_channel_id:
            return

        lock = self.get_guild_lock(message.guild.id)

        async with lock:
            if not contains_valid_alchemy_data(message.content):
                try:
                    await message.delete()
                except (discord.Forbidden, discord.NotFound):
                    return

                if isinstance(message.author, discord.Member):
                    await self.send_invalid_message_dm(
                        message.author,
                        message.channel,
                    )

                return

            results = parse_alchemy(message.content)

            time_text = datetime.now(
                ZoneInfo("Asia/Seoul")
            ).strftime("%Y-%m-%d %H:%M")

            result_text = build_result_text(
                results,
                message.author.display_name,
                time_text,
            )

            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound):
                return

            await self.delete_previous_results(message.channel)
            await self.delete_alchemy_alerts(message.channel)
            await message.channel.send(result_text)

            await send_use_log(
                bot=self.bot,
                title="🧪 연금 분석",
                user=message.author,
                guild=message.guild,
                channel=message.channel
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(Alchemy(bot))