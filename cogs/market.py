import asyncio
import sqlite3
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from market_stats import (
    get_item_stats,
    get_matching_items,
)

from utils.channel_manager import (
    get_channel_id,
    remove_channel_id,
    set_channel_id,
)


DB_PATH = (
    Path(__file__).resolve().parent.parent
    / "market.db"
)


def create_market_embed(
    stats: dict,
) -> discord.Embed:
    item_name = stats["item_name"]

    if stats["mode"] == "last_trade":
        latest_trade_date = stats["latest_trade_date"]

        embed = discord.Embed(
            title=f"💰 {item_name} 시세",
            color=discord.Color.gold(),
        )

        embed.add_field(
            name="최근 거래 시세",
            value=(
                f"**개당 {stats['unit_price']:,}냥**"
            ),
            inline=False,
        )

        embed.add_field(
            name=f"📦 {stats['quantity']}개 기준",
            value=f"**{stats['total_price']:,}냥**",
            inline=False,
        )

        from market_stats import format_days_ago

        embed.add_field(
            name="📅 마지막 거래",
            value=(
                f"{latest_trade_date.strftime('%Y-%m-%d %H:%M')}\n"
                f"({format_days_ago(latest_trade_date)})"
            ),
            inline=False,
        )

        embed.add_field(
            name="⚠️ 거래 안내",
            value=(
                "최근 72시간 동안 거래 내역이 없습니다.\n"
                "최근 거래를 참고해주세요."
            ),
            inline=False,
        )

        embed.set_footer(
            text="통합거래소 구매 완료 내역 기준"
        )

        return embed

    embed = discord.Embed(
        title=f"💰 {item_name} 시세",
        color=discord.Color.gold(),
    )

    embed.add_field(
        name="개당 평균가",
        value=(
            f"**{stats['average_unit_price']:,}냥**"
        ),
        inline=False,
    )

    embed.add_field(
        name=(
            f"📦 {stats['representative_quantity']}개 기준"
        ),
        value=(
            f"평균 **{stats['average_total']:,}냥**\n"
            f"범위 "
            f"{stats['minimum_total']:,}"
            f" ~ "
            f"{stats['maximum_total']:,}냥"
        ),
        inline=False,
    )

    embed.add_field(
        name="📊 거래 정보",
        value=(
            f"거래 범위 "
            f"{stats['minimum_unit_price']:,}"
            f" ~ "
            f"{stats['maximum_unit_price']:,}냥\n"
            f"거래 건수 "
            f"**{stats['used_trade_count']}건**\n"
            f"최근 거래 "
            f"{stats['latest_trade_date'].strftime('%Y-%m-%d %H:%M')}"
        ),
        inline=False,
    )

    notice_lines = [
        "통합거래소 구매 완료 내역 기준",
        "최근 최대 72시간 데이터로 계산",
    ]

    if stats["excluded_trade_count"] > 0:
        notice_lines.append(
            f"이상치 {stats['excluded_trade_count']}건 제외"
        )

    embed.set_footer(
        text=" · ".join(notice_lines)
    )

    if stats["used_trade_count"] <= 4:
        embed.add_field(
            name="⚠️ 거래 데이터 안내",
            value=(
                f"거래 데이터가 "
                f"{stats['used_trade_count']}건으로 적습니다.\n"
                "시세 참고 후 신중하게 거래해주세요."
            ),
            inline=False,
        )

    return embed


class MarketSelect(discord.ui.Select):
    def __init__(
        self,
        cog: "Market",
        item_names: list[str],
        user_id: int,
    ):
        self.cog = cog
        self.user_id = user_id

        options = [
            discord.SelectOption(
                label=item_name[:100],
                value=item_name,
            )
            for item_name in item_names[:25]
        ]

        super().__init__(
            placeholder="확인할 아이템을 선택해주세요.",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ 검색한 사용자만 선택할 수 있습니다.",
                ephemeral=True,
            )
            return

        selected_item = self.values[0]

        stats = self.cog.get_stats(
            selected_item
        )

        if stats is None:
            await interaction.response.edit_message(
                content=(
                    "🔎 시세 정보를 찾을 수 없습니다."
                ),
                embed=None,
                view=None,
            )
            return

        embed = create_market_embed(stats)

        await interaction.response.edit_message(
            content=None,
            embed=embed,
            view=None,
        )


class MarketSelectView(discord.ui.View):
    def __init__(
        self,
        cog: "Market",
        item_names: list[str],
        user_id: int,
    ):
        super().__init__(timeout=60)

        self.add_item(
            MarketSelect(
                cog=cog,
                item_names=item_names,
                user_id=user_id,
            )
        )


class Market(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
    ):
        self.bot = bot

    market_group = app_commands.Group(
        name="시세",
        description="시세 조회 채널을 설정합니다.",
    )

    @market_group.command(
        name="채널설정",
        description="현재 채널을 시세 조회 채널로 설정합니다.",
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
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

        if not isinstance(
            interaction.channel,
            discord.TextChannel,
        ):
            await interaction.response.send_message(
                "❌ 일반 텍스트 채널에서만 설정할 수 있습니다.",
                ephemeral=True,
            )
            return

        set_channel_id(
            interaction.guild.id,
            "market",
            interaction.channel.id,
        )

        await interaction.response.send_message(
            (
                f"✅ {interaction.channel.mention} 채널을 "
                "시세 조회 채널로 설정했습니다."
            ),
            ephemeral=True,
        )

        guide_embed = discord.Embed(
            title="💰 도동봇 시세 조회 사용법",
            description=(
                "조회할 **아이템명만 입력**해주세요.\n\n"
                "예시\n"
                "• `레몬`\n"
                "• `셜커`\n"
                "• `금별 아스파라거스`\n\n"
                "검색 결과가 여러 개면 목록에서 "
                "아이템을 선택할 수 있습니다."
            ),
            color=discord.Color.gold(),
        )

        guide_embed.set_footer(
            text="통합거래소 구매 완료 내역 기준"
        )

        await interaction.channel.send(
            embed=guide_embed
        )

    @market_group.command(
        name="채널확인",
        description="현재 설정된 시세 조회 채널을 확인합니다.",
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
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
            "market",
        )

        if channel_id is None:
            await interaction.response.send_message(
                "❌ 현재 설정된 시세 조회 채널이 없습니다.",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(
            channel_id
        )

        if channel is None:
            await interaction.response.send_message(
                "⚠️ 설정된 시세 조회 채널을 찾을 수 없습니다.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            (
                f"✅ 현재 시세 조회 채널은 "
                f"{channel.mention}입니다."
            ),
            ephemeral=True,
        )

    @market_group.command(
        name="채널해제",
        description="현재 설정된 시세 조회 채널을 해제합니다.",
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
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
            "market",
        )

        if not removed:
            await interaction.response.send_message(
                "❌ 현재 설정된 시세 조회 채널이 없습니다.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "✅ 시세 조회 채널 설정을 해제했습니다.",
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

        if not isinstance(
            message.channel,
            discord.TextChannel,
        ):
            return

        configured_channel_id = get_channel_id(
            message.guild.id,
            "market",
        )

        if configured_channel_id is None:
            return

        if message.channel.id != configured_channel_id:
            return

        keyword = message.content.strip()

        try:
            await message.delete()
        except (
            discord.Forbidden,
            discord.NotFound,
            discord.HTTPException,
        ):
            pass

        searching_message = await message.channel.send(
            "🔍 시세 정보를 검색하고 있습니다..."
        )

        await asyncio.sleep(0.3)

        if not keyword:
            await self.show_not_found(
                searching_message
            )
            return

        matched_items = self.get_matches(
            keyword
        )

        if not matched_items:
            await self.show_not_found(
                searching_message
            )
            return

        if len(matched_items) == 1:
            stats = self.get_stats(
                matched_items[0]
            )

            if stats is None:
                await self.show_not_found(
                    searching_message
                )
                return

            embed = create_market_embed(stats)

            await searching_message.edit(
                content=None,
                embed=embed,
            )
            return

        description = "\n".join(
            f"• {item_name}"
            for item_name in matched_items[:25]
        )

        selection_embed = discord.Embed(
            title="🔎 여러 아이템이 검색되었습니다.",
            description=(
                f"{description}\n\n"
                "아래 목록에서 확인할 아이템을 선택해주세요."
            ),
            color=discord.Color.blurple(),
        )

        view = MarketSelectView(
            cog=self,
            item_names=matched_items,
            user_id=message.author.id,
        )

        await searching_message.edit(
            content=None,
            embed=selection_embed,
            view=view,
        )

    def get_matches(
        self,
        keyword: str,
    ) -> list[str]:
        if not DB_PATH.exists():
            return []

        connection = sqlite3.connect(
            DB_PATH
        )

        try:
            return get_matching_items(
                connection,
                keyword,
            )
        finally:
            connection.close()

    def get_stats(
        self,
        item_name: str,
    ) -> dict | None:
        if not DB_PATH.exists():
            return None

        connection = sqlite3.connect(
            DB_PATH
        )

        try:
            return get_item_stats(
                connection,
                item_name,
            )
        finally:
            connection.close()

    async def show_not_found(
        self,
        response_message: discord.Message,
    ) -> None:
        embed = discord.Embed(
            title="🔎 시세 정보를 찾을 수 없습니다.",
            description=(
                "아이템명을 다시 확인해주세요.\n"
                "예: 레몬, 셜커, 금별 아스파라거스\n\n"
                "※ 최근 거래 내역이 없거나 아직 "
                "수집되지 않은 아이템은 "
                "조회되지 않을 수 있습니다."
            ),
            color=discord.Color.red(),
        )

        await response_message.edit(
            content=None,
            embed=embed,
        )

        await asyncio.sleep(5)

        try:
            await response_message.delete()
        except (
            discord.Forbidden,
            discord.NotFound,
            discord.HTTPException,
        ):
            pass

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


async def setup(
    bot: commands.Bot,
) -> None:
    await bot.add_cog(
        Market(bot)
    )