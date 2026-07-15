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


FOOD_TIERS = {
    "아스파라거스 샐러드": 1,
    "갈릭 포테이토 콩피": 1,
    "레몬 당근 라페": 1,
    "어니언 포테이토 그라탱": 1,
    "고로케": 1,

    "갈릭 아스파라거스 피클": 2,
    "시트러스 어니언 스튜": 2,
    "어니언 감자조림": 2,
    "아스파라거스 라페": 2,

    "파프리카 비프 스튜": 3,
    "피치 레몬 치킨": 3,
    "허브 램 플래터": 3,
    "스파이시 갈릭 포크": 3,

    "비프 라구 파이": 4,
    "복숭아 치킨 타르트": 4,
    "키슈 파이": 4,
    "갈릭 포크 크로켓": 4,

    "크리미 파프리카 비프플레이트": 5,
    "시트러스 피치 치킨램": 5,
    "그린 허브 램플": 5,
    "스파이시 포크라이스": 5,
}


PRICE_RANGE = {
    1: {
        "무별": (48, 62),
        "은별": (62, 72),
        "금별": (72, 82),
    },
    2: {
        "무별": (69, 90),
        "은별": (90, 104),
        "금별": (104, 117),
    },
    3: {
        "무별": (120, 156),
        "은별": (156, 180),
        "금별": (180, 204),
    },
    4: {
        "무별": (191, 248),
        "은별": (248, 287),
        "금별": (287, 325),
    },
}


TIER_5_PRICE_RANGE = {
    "크리미 파프리카 비프플레이트": {
        "무별": (209, 272),
        "은별": (272, 314),
        "금별": (314, 355),
    },
    "스파이시 포크라이스": {
        "무별": (209, 272),
        "은별": (272, 314),
        "금별": (314, 355),
    },
    "시트러스 피치 치킨램": {
        "무별": (185, 241),
        "은별": (241, 278),
        "금별": (278, 315),
    },
    "그린 허브 램플": {
        "무별": (185, 241),
        "은별": (241, 278),
        "금별": (278, 315),
    },
}


COOKING_PATTERN = re.compile(
    r"\[(.*?)\]\s*\|\s*(\d+)\s*→\s*(\d+)"
)


COOKING_ALERT_BEFORE_TEXT = (
    "🔔 **만들어둔 음식 파셨나요?**\n\n"
    "변동상점 갱신까지 10분 남았습니다!"
)

COOKING_ALERT_UPDATED_TEXT = (
    "🍳 **요리 변동상점이 갱신되었습니다!**\n\n"
    "새로운 시세를 확인해보세요."
)

COOKING_ALERT_PREFIXES = (
    "🔔 **만들어둔 음식 파셨나요?**",
    "🍳 **요리 변동상점이 갱신되었습니다!**",
)


def get_status(price: int, low: int, high: int) -> str:
    mid = (low + high) / 2
    high_point = low + (high - low) * 0.9

    if price >= high_point:
        return "고점"

    if price >= mid:
        return "추천"

    return "저점"


def get_food_grade(raw_name: str) -> str:
    if "🩶" in raw_name:
        return "은별"

    if "🌟" in raw_name:
        return "금별"

    return "무별"


def clean_food_name(raw_name: str) -> str:
    return raw_name.replace("🩶", "").replace("🌟", "").strip()


def get_price_range(
    name: str,
    tier: int,
    grade: str,
) -> tuple[int, int] | None:
    if tier == 5:
        food_ranges = TIER_5_PRICE_RANGE.get(name)

        if food_ranges is None:
            return None

        return food_ranges.get(grade)

    tier_ranges = PRICE_RANGE.get(tier)

    if tier_ranges is None:
        return None

    return tier_ranges.get(grade)


def contains_valid_cooking_data(text: str) -> bool:
    matches = COOKING_PATTERN.findall(text)

    if not matches:
        return False

    for raw_name, _, _ in matches:
        name = clean_food_name(raw_name)

        if name in FOOD_TIERS:
            return True

    return False


def parse_cooking(text: str) -> dict:
    results = {
        "고점": {},
        "은별고점": {},
        "금별고점": {},
        "추천": {},
    }

    for raw_name, _, current_price in COOKING_PATTERN.findall(text):
        grade = get_food_grade(raw_name)
        name = clean_food_name(raw_name)
        tier = FOOD_TIERS.get(name)

        if tier is None:
            continue

        price_range = get_price_range(name, tier, grade)

        if price_range is None:
            continue

        low, high = price_range
        price = int(current_price)
        status = get_status(price, low, high)

        if grade == "무별":
            if status == "저점":
                continue

            results[status].setdefault(
                (tier, low, high),
                [],
            ).append(
                f"🍳 **{name}** - {price}원"
            )
            continue

        if status != "고점":
            continue

        result_key = "은별고점" if grade == "은별" else "금별고점"
        output_emoji = "⚪" if grade == "은별" else "🟡"

        results[result_key].setdefault(
            (tier, low, high),
            [],
        ).append(
            f"{output_emoji} **{name}** - {price}원"
        )

    return results


def build_result_text(
    results: dict,
    updater_name: str,
    time_text: str,
) -> str:
    parts = ["🍳 **요리 변동상점**"]

    parts.append("\n🔥 고점")

    has_high_items = any(
        results.get(key)
        for key in ("고점", "은별고점", "금별고점")
    )

    if not has_high_items:
        parts.append("없음")
    else:
        for (tier, low, high), items in sorted(
            results["고점"].items()
        ):
            parts.append(
                f"\n【{tier}차 (무별)】 ({low}~{high}원)"
            )
            parts.extend(items)

        for (tier, low, high), items in sorted(
            results["은별고점"].items()
        ):
            parts.append(
                f"\n【{tier}차 (은별)】 ({low}~{high}원)"
            )
            parts.extend(items)

        for (tier, low, high), items in sorted(
            results["금별고점"].items()
        ):
            parts.append(
                f"\n【{tier}차 (금별)】 ({low}~{high}원)"
            )
            parts.extend(items)

    parts.append("\n━━━━━━━━━━━━━━")
    parts.append("\n⭐ 추천")

    if not results.get("추천"):
        parts.append("없음")
    else:
        for (tier, low, high), items in sorted(
            results["추천"].items()
        ):
            parts.append(
                f"\n【{tier}차 (무별)】 ({low}~{high}원)"
            )
            parts.extend(items)

    parts.append("\n━━━━━━━━━━━━━━")
    parts.append(
        "\n※ 중간값 이하의 음식은 표시되지 않습니다."
    )
    parts.append(
        "※ 추천은 변동 시세의 중간값 이상, "
        "고점은 상위 10% 구간을 기준으로 선정됩니다."
    )

    parts.append("")
    parts.append(f"> 업데이트 : {updater_name} / {time_text}")

    return "\n".join(parts)


class Cooking(commands.Cog):
    cooking_group = app_commands.Group(
        name="요리",
        description="요리 변동상점 기능입니다.",
    )

    channel_group = app_commands.Group(
        name="변동채널",
        description="요리 변동상점 채널을 관리합니다.",
        parent=cooking_group,
    )

    alert_group = app_commands.Group(
        name="알림",
        description="요리 변동상점 갱신 알림을 관리합니다.",
        parent=cooking_group,
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_locks: dict[int, asyncio.Lock] = {}
        self.last_cooking_alert_key: str | None = None
        self.cooking_alert_task.start()

    def cog_unload(self) -> None:
        self.cooking_alert_task.cancel()

    def get_guild_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self.update_locks:
            self.update_locks[guild_id] = asyncio.Lock()

        return self.update_locks[guild_id]

    @channel_group.command(
        name="설정",
        description="현재 채널을 요리 변동상점 채널로 설정합니다.",
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
            "cooking",
            interaction.channel.id,
        )

        await interaction.response.send_message(
            "✅ 요리 변동상점 채널을 설정했습니다.\n\n"
            f"설정된 채널: {interaction.channel.mention}\n\n"
            "이제 동글랜드의 요리 변동상점 내용을 "
            "이 채널에 그대로 붙여넣으면 자동으로 분석됩니다.",
            ephemeral=True,
        )

    @channel_group.command(
        name="확인",
        description="현재 설정된 요리 변동상점 채널을 확인합니다.",
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
            "cooking",
        )

        if channel_id is None:
            await interaction.response.send_message(
                "❌ 현재 설정된 요리 변동상점 채널이 없습니다.\n\n"
                "원하는 채널에서 `/요리 변동채널 설정`을 "
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
            "🍳 현재 요리 변동상점 채널\n\n"
            f"{channel.mention}",
            ephemeral=True,
        )

    @channel_group.command(
        name="해제",
        description="요리 변동상점 채널 설정을 해제합니다.",
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
            "cooking",
        )

        if not removed:
            await interaction.response.send_message(
                "❌ 현재 설정된 요리 변동상점 채널이 없습니다.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "✅ 요리 변동상점 채널 설정을 해제했습니다.",
            ephemeral=True,
        )

    @alert_group.command(
        name="켜기",
        description="요리 변동상점 갱신 알림을 켭니다.",
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
            "cooking",
        )

        if channel_id is None:
            await interaction.response.send_message(
                "❌ 먼저 `/요리 변동채널 설정`으로 "
                "요리 변동상점 채널을 설정해주세요.",
                ephemeral=True,
            )
            return

        set_setting_enabled(
            interaction.guild.id,
            "cooking_alert",
            True,
        )

        await interaction.response.send_message(
            "✅ 요리 변동상점 갱신 알림을 켰습니다.\n\n"
            "갱신 10분 전과 갱신 정각에 "
            "설정된 요리 변동상점 채널로 알림을 보냅니다.",
            ephemeral=True,
        )

    @alert_group.command(
        name="끄기",
        description="요리 변동상점 갱신 알림을 끕니다.",
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
            "cooking_alert",
            False,
        )

        channel = await self.get_cooking_channel(interaction.guild)

        if channel is not None:
            await self.delete_cooking_alerts(channel)

        await interaction.response.send_message(
            "✅ 요리 변동상점 갱신 알림을 껐습니다.",
            ephemeral=True,
        )

    @alert_group.command(
        name="확인",
        description="요리 변동상점 갱신 알림 상태를 확인합니다.",
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
            "cooking_alert",
        )

        status_text = "켜짐" if enabled else "꺼짐"

        await interaction.response.send_message(
            "🍳 요리 변동상점 갱신 알림\n\n"
            f"현재 상태: **{status_text}**",
            ephemeral=True,
        )

    async def get_cooking_channel(
        self,
        guild: discord.Guild,
    ) -> discord.TextChannel | None:
        channel_id = get_channel_id(guild.id, "cooking")

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

    async def delete_cooking_alerts(
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
                    COOKING_ALERT_PREFIXES
                ):
                    continue

                try:
                    await previous_message.delete()
                except (discord.Forbidden, discord.NotFound):
                    pass
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def send_cooking_alert(
        self,
        channel: discord.TextChannel,
        content: str,
    ) -> None:
        await self.delete_cooking_alerts(channel)

        try:
            await channel.send(content)
        except (discord.Forbidden, discord.HTTPException):
            pass

    @tasks.loop(seconds=30)
    async def cooking_alert_task(self) -> None:
        now = datetime.now(ZoneInfo("Asia/Seoul"))

        alert_kind: str | None = None
        alert_text: str | None = None

        if now.minute == 50 and now.hour % 3 == 2:
            alert_kind = "before"
            alert_text = COOKING_ALERT_BEFORE_TEXT
        elif now.minute == 0 and now.hour % 3 == 0:
            alert_kind = "updated"
            alert_text = COOKING_ALERT_UPDATED_TEXT

        if alert_kind is None or alert_text is None:
            return

        alert_key = now.strftime(f"%Y-%m-%d-%H-{alert_kind}")

        if self.last_cooking_alert_key == alert_key:
            return

        self.last_cooking_alert_key = alert_key

        for guild in self.bot.guilds:
            if not get_setting_enabled(guild.id, "cooking_alert"):
                continue

            channel = await self.get_cooking_channel(guild)

            if channel is None:
                continue

            await self.send_cooking_alert(channel, alert_text)

    @cooking_alert_task.before_loop
    async def before_cooking_alert_task(self) -> None:
        await self.bot.wait_until_ready()

    async def send_invalid_message_dm(
        self,
        member: discord.Member,
        channel: discord.TextChannel,
    ) -> None:
        try:
            await member.send(
                "❌ 요리 변동상점 채널에는 "
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
                "🍳 **요리 변동상점**"
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
            "cooking",
        )

        if configured_channel_id is None:
            return

        if message.channel.id != configured_channel_id:
            return

        lock = self.get_guild_lock(message.guild.id)

        async with lock:
            if not contains_valid_cooking_data(message.content):
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

            results = parse_cooking(message.content)

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
            await self.delete_cooking_alerts(message.channel)
            await message.channel.send(result_text)

            await send_use_log(
                bot=self.bot,
                title="🍳 요리 분석",
                user=message.author,
                guild=message.guild,
                channel=message.channel
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(Cooking(bot))