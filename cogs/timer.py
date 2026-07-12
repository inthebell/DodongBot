import asyncio
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from utils.channel_manager import (
    get_channel_id,
    remove_channel_id,
    set_channel_id,
)


KST = timezone(timedelta(hours=9))

TIMER_TYPES = {
    "농부": {
        "keywords": {"농부", "ㄴㅂ"},
        "seconds": 17 * 60,
        "emoji": "🌱",
        "time_text": "17분",
        "start_name": "농부",
        "complete_message": (
            "{mention}님 🌾 작물이 모두 자랐습니다!\n"
            "어서 수확하러 가세요!"
        ),
    },
    "요리": {
        "keywords": {"요리", "ㅇㄹ"},
        "seconds": 26 * 60 + 40,
        "emoji": "🍳",
        "time_text": "26분 40초",
        "start_name": "요리",
        "complete_message": (
            "{mention}님 🍳 요리 제작이 완료되었습니다!\n"
            "작업대를 확인해 보세요!"
        ),
    },
    "다이버": {
        "keywords": {"다이버", "ㄷㅇㅂ"},
        "seconds": 60 * 60,
        "emoji": "🤿",
        "time_text": "1시간",
        "start_name": "다이버 토템",
        "complete_message": (
            "{mention}님 🤿 1시간이 지났습니다!\n"
            "다이버 토템을 다시 설치할 수 있습니다."
        ),
    },
    "호감도": {
        "keywords": {"호감도", "ㅎㄱㄷ"},
        "seconds": 6 * 60 * 60,
        "emoji": "💝",
        "time_text": "6시간",
        "start_name": "호감도",
        "complete_message": (
            "{mention}님 💝 6시간이 지났습니다!\n"
            "주민들에게 다시 선물할 수 있습니다."
        ),
    },
}


class Timer(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # (서버 ID, 사용자 ID, 타이머 종류)별 실행 작업
        self.timer_tasks: dict[tuple[int, int, str], asyncio.Task] = {}

        # 실행 중인 타이머 정보
        self.active_timers: dict[tuple[int, int, str], dict] = {}

        # 사용자별로 가장 최근에 전송된 완료 메시지
        self.last_complete_messages: dict[tuple[int, int], int] = {}

    timer_group = app_commands.Group(
        name="타이머",
        description="타이머 채널을 설정합니다.",
    )

    @timer_group.command(
        name="채널설정",
        description="현재 채널을 타이머 채널로 설정합니다.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ 일반 텍스트 채널에서만 설정할 수 있습니다.",
                ephemeral=True,
            )
            return

        set_channel_id(
            interaction.guild.id,
            "timer",
            interaction.channel.id,
        )

        await interaction.response.send_message(
            f"✅ {interaction.channel.mention} 채널을 타이머 채널로 설정했습니다.",
            ephemeral=True,
        )

        guide_message = await interaction.channel.send(
            "## ⏰ 도동봇 타이머 사용법\n\n"
            "아래 단어를 입력하면 개인 타이머가 시작됩니다.\n\n"
            "🌱 **농부** 또는 `ㄴㅂ` · 17분\n"
            "🍳 **요리** 또는 `ㅇㄹ` · 26분 40초\n"
            "🤿 **다이버** 또는 `ㄷㅇㅂ` · 1시간\n"
            "💝 **호감도** 또는 `ㅎㄱㄷ` · 6시간\n\n"
            "현재 남은 시간을 확인하려면 **타이머**라고 입력해 주세요."
        )

        try:
            await guide_message.pin(
                reason="도동봇 타이머 사용법 안내",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "⚠️ 타이머 채널은 설정했지만 안내 메시지를 고정하지 못했습니다.\n"
                "도동봇의 메시지 관리 권한을 확인해 주세요.",
                ephemeral=True,
            )
        except discord.HTTPException:
            pass

    @timer_group.command(
        name="채널확인",
        description="현재 설정된 타이머 채널을 확인합니다.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def check_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        channel_id = get_channel_id(
            interaction.guild.id,
            "timer",
        )

        if channel_id is None:
            await interaction.response.send_message(
                "❌ 현재 설정된 타이머 채널이 없습니다.",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(channel_id)

        if channel is None:
            await interaction.response.send_message(
                "⚠️ 설정된 타이머 채널을 찾을 수 없습니다.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"✅ 현재 타이머 채널은 {channel.mention}입니다.",
            ephemeral=True,
        )

    @timer_group.command(
        name="채널해제",
        description="현재 설정된 타이머 채널을 해제합니다.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        removed = remove_channel_id(
            interaction.guild.id,
            "timer",
        )

        if not removed:
            await interaction.response.send_message(
                "❌ 현재 설정된 타이머 채널이 없습니다.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "✅ 타이머 채널 설정을 해제했습니다.",
            ephemeral=True,
        )

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
            "timer",
        )

        if configured_channel_id is None:
            return

        if message.channel.id != configured_channel_id:
            return

        content = message.content.strip()

        if content == "타이머":
            await self.show_timers(message)
            return

        timer_name = self.find_timer_name(content)

        if timer_name is None:
            return

        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass

        await self.start_timer(
            message=message,
            timer_name=timer_name,
        )

    def find_timer_name(
        self,
        content: str,
    ) -> str | None:
        for timer_name, timer_data in TIMER_TYPES.items():
            if content in timer_data["keywords"]:
                return timer_name

        return None

    async def start_timer(
        self,
        message: discord.Message,
        timer_name: str,
    ) -> None:
        if message.guild is None:
            return

        timer_data = TIMER_TYPES[timer_name]

        key = (
            message.guild.id,
            message.author.id,
            timer_name,
        )

        user_key = (
            message.guild.id,
            message.author.id,
        )

        # 같은 종류의 기존 타이머가 있으면 새 시간으로 교체
        old_task = self.timer_tasks.pop(key, None)

        if old_task is not None:
            old_task.cancel()

        old_timer = self.active_timers.pop(key, None)

        if old_timer is not None:
            old_start_message = old_timer.get("start_message")

            if old_start_message is not None:
                try:
                    await old_start_message.delete()
                except (
                    discord.Forbidden,
                    discord.NotFound,
                    discord.HTTPException,
                ):
                    pass

        # 해당 사용자의 이전 완료 메시지 삭제
        old_complete_message_id = self.last_complete_messages.pop(
            user_key,
            None,
        )

        if old_complete_message_id is not None:
            try:
                old_complete_message = await message.channel.fetch_message(
                    old_complete_message_id
                )
                await old_complete_message.delete()
            except (
                discord.Forbidden,
                discord.NotFound,
                discord.HTTPException,
            ):
                pass

        start_message = await message.channel.send(
            f"{timer_data['emoji']} "
            f"{message.author.mention}님의 "
            f"{timer_data['start_name']} 타이머를 시작했습니다.\n\n"
            f"{timer_data['time_text']} 뒤에 알려드릴게요!",
            allowed_mentions=discord.AllowedMentions(
                users=True,
                roles=False,
                everyone=False,
            ),
        )

        end_time = datetime.now(KST) + timedelta(
            seconds=timer_data["seconds"]
        )

        self.active_timers[key] = {
            "end_time": end_time,
            "channel_id": message.channel.id,
            "user_id": message.author.id,
            "start_message": start_message,
        }

        task = asyncio.create_task(
            self.finish_timer(
                key=key,
                timer_name=timer_name,
            )
        )

        self.timer_tasks[key] = task

    async def finish_timer(
        self,
        key: tuple[int, int, str],
        timer_name: str,
    ) -> None:
        timer_data = TIMER_TYPES[timer_name]
        timer_info = self.active_timers.get(key)

        if timer_info is None:
            return

        try:
            await asyncio.sleep(timer_data["seconds"])
        except asyncio.CancelledError:
            return

        timer_info = self.active_timers.pop(key, None)
        self.timer_tasks.pop(key, None)

        if timer_info is None:
            return

        start_message = timer_info.get("start_message")

        if start_message is not None:
            try:
                await start_message.delete()
            except (
                discord.Forbidden,
                discord.NotFound,
                discord.HTTPException,
            ):
                pass

        channel = self.bot.get_channel(timer_info["channel_id"])

        if channel is None:
            try:
                channel = await self.bot.fetch_channel(
                    timer_info["channel_id"]
                )
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return

        mention = f"<@{timer_info['user_id']}>"

        complete_message = await channel.send(
            timer_data["complete_message"].format(
                mention=mention
            ),
            allowed_mentions=discord.AllowedMentions(
                users=True,
                roles=False,
                everyone=False,
            ),
        )

        user_key = (
            key[0],
            key[1],
        )

        self.last_complete_messages[user_key] = complete_message.id

    async def show_timers(
        self,
        message: discord.Message,
    ) -> None:
        if message.guild is None:
            return

        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass

        now = datetime.now(KST)
        timer_lines = []

        for timer_name, timer_data in TIMER_TYPES.items():
            key = (
                message.guild.id,
                message.author.id,
                timer_name,
            )

            timer_info = self.active_timers.get(key)

            if timer_info is None:
                continue

            remaining_seconds = int(
                (timer_info["end_time"] - now).total_seconds()
            )

            if remaining_seconds <= 0:
                continue

            remaining_text = self.format_remaining_time(
                remaining_seconds
            )

            timer_lines.append(
                f"{timer_data['emoji']} "
                f"{timer_name} · {remaining_text} 남음"
            )

        if not timer_lines:
            response = await message.channel.send(
                f"{message.author.mention}님 ⏰ "
                "현재 실행 중인 타이머가 없습니다.",
                allowed_mentions=discord.AllowedMentions(
                    users=True,
                    roles=False,
                    everyone=False,
                ),
            )
        else:
            response = await message.channel.send(
                f"⏰ **{message.author.display_name}님의 실행 중인 타이머**\n\n"
                + "\n".join(timer_lines)
            )

        await asyncio.sleep(10)

        try:
            await response.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass

    def format_remaining_time(
        self,
        seconds: int,
    ) -> str:
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []

        if hours:
            parts.append(f"{hours}시간")

        if minutes:
            parts.append(f"{minutes}분")

        if seconds or not parts:
            parts.append(f"{seconds}초")

        return " ".join(parts)

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(
            error,
            app_commands.MissingPermissions,
        ):
            await interaction.response.send_message(
                "❌ 이 명령어는 관리자만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        raise error


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Timer(bot))