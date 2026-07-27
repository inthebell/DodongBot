import sqlite3
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from utils.channel_manager import (
    get_channel_id,
    remove_channel_id,
    set_channel_id,
)


DODONG_GUILD_ID = 1517850860322029618
OWNER_ID = 478834154595811328


DB_PATH = (
    Path(__file__).resolve().parent.parent
    / "market.db"
)


class FleaMarketRegisterModal(discord.ui.Modal):
    def __init__(
        self,
        market_type: str,
    ):
        super().__init__(
            title=f"플리마켓 {market_type} 홍보 등록"
        )

        self.market_type = market_type

        self.category = discord.ui.TextInput(
            label="분류",
            placeholder="예) 작물",
            required=True,
            max_length=10,
        )

        self.keywords = discord.ui.TextInput(
            label="세부 검색 키워드",
            placeholder="예) 레몬, 감자, 당근",
            required=True,
            max_length=60,
        )

        self.description = discord.ui.TextInput(
            label="홍보 문구",
            placeholder="예) 3티어 작물 판매합니다.",
            required=True,
            max_length=60,
        )

        self.waypoint = discord.ui.TextInput(
            label="이정표",
            placeholder="예) /이정표 도동마켓",
            required=True,
            max_length=50,
        )

        self.add_item(self.category)
        self.add_item(self.keywords)
        self.add_item(self.description)
        self.add_item(self.waypoint)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        category = self.category.value.strip()

        keywords = [
            keyword.strip()
            for keyword in self.keywords.value.replace(
                "，",
                ",",
            ).split(",")
            if keyword.strip()
        ]

        if len(keywords) > 5:
            await interaction.response.send_message(
                "❌ 세부 키워드는 최대 5개까지 입력할 수 있습니다.",
                ephemeral=True,
            )
            return

        if any(
            len(keyword) > 10
            for keyword in keywords
        ):
            await interaction.response.send_message(
                "❌ 각 세부 키워드는 최대 10자까지 입력할 수 있습니다.",
                ephemeral=True,
            )
            return

        if not keywords:
            await interaction.response.send_message(
                "❌ 세부 키워드를 1개 이상 입력해주세요.",
                ephemeral=True,
            )
            return

        normalized_keywords = " · ".join(
            dict.fromkeys(keywords)
        )

        description = " ".join(
            self.description.value.split()
        )

        waypoint = " ".join(
            self.waypoint.value.split()
        )

        type_emoji = (
            "🟢"
            if self.market_type == "판매"
            else "🔴"
        )

        embed = discord.Embed(
            title="✅ 플리마켓 신청 내용 확인",
            description=(
                "현재는 테스트 단계로 아직 DB에 저장되지 않습니다."
            ),
            color=(
                discord.Color.green()
                if self.market_type == "판매"
                else discord.Color.red()
            ),
        )

        embed.add_field(
            name="거래 구분",
            value=f"{type_emoji} {self.market_type}",
            inline=False,
        )

        embed.add_field(
            name="분류",
            value=category,
            inline=False,
        )

        embed.add_field(
            name="세부 키워드",
            value=normalized_keywords,
            inline=False,
        )

        embed.add_field(
            name="검색 결과 미리보기",
            value=(
                f"{type_emoji} {self.market_type}\n"
                f"📢 {description}\n"
                f"📍 {waypoint}"
            ),
            inline=False,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )


class FleaMarketRegisterView(discord.ui.View):
    def __init__(
        self,
        user_id: int,
    ):
        super().__init__(timeout=60)
        self.user_id = user_id

    async def check_user(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "❌ 신청한 사용자만 선택할 수 있습니다.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(
        label="판매",
        emoji="🟢",
        style=discord.ButtonStyle.success,
    )
    async def select_sell(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not await self.check_user(interaction):
            return

        await interaction.response.send_modal(
            FleaMarketRegisterModal("판매")
        )

    @discord.ui.button(
        label="구매",
        emoji="🔴",
        style=discord.ButtonStyle.danger,
    )
    async def select_buy(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not await self.check_user(interaction):
            return

        await interaction.response.send_modal(
            FleaMarketRegisterModal("구매")
        )



class FleaMarket(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
    ):
        self.bot = bot
        self.create_database()

    fleamarket_group = app_commands.Group(
        name="플리마켓",
        description="플리마켓 홍보 및 검색 기능입니다.",
        guild_ids=[DODONG_GUILD_ID],
        default_permissions=discord.Permissions(
            administrator=True
        ),
    )

    def create_database(
        self,
    ) -> None:
        connection = sqlite3.connect(DB_PATH)

        try:
            cursor = connection.cursor()

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS flea_market (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '',
                    keywords TEXT NOT NULL,
                    description TEXT NOT NULL,
                    waypoint TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    views INTEGER NOT NULL DEFAULT 0
                )
                """
            )

            cursor.execute(
                "PRAGMA table_info(flea_market)"
            )
            columns = {
                row[1]
                for row in cursor.fetchall()
            }

            if "category" not in columns:
                cursor.execute(
                    "ALTER TABLE flea_market "
                    "ADD COLUMN category TEXT NOT NULL DEFAULT ''"
                )

            connection.commit()

        finally:
            connection.close()

    def is_owner(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        return interaction.user.id == OWNER_ID

    @fleamarket_group.command(
        name="홍보등록",
        description="플리마켓 홍보 등록 신청서를 작성합니다.",
    )
    async def register_ad(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        if interaction.guild.id != DODONG_GUILD_ID:
            await interaction.response.send_message(
                "❌ 현재 테스트 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🏪 플리마켓 홍보 등록",
            description=(
                "등록할 홍보의 거래 구분을 선택해주세요.\n\n"
                "🟢 판매\n"
                "🔴 구매"
            ),
            color=discord.Color.green(),
        )

        view = FleaMarketRegisterView(
            user_id=interaction.user.id,
        )

        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True,
        )

    @fleamarket_group.command(
        name="채널설정",
        description="현재 채널을 플리마켓 검색 채널로 설정합니다.",
    )
    async def set_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not self.is_owner(interaction):
            await interaction.response.send_message(
                "❌ 이 명령어는 도동봇 운영자만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        if interaction.guild.id != DODONG_GUILD_ID:
            await interaction.response.send_message(
                "❌ 현재 테스트 서버에서만 사용할 수 있습니다.",
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
            "fleamarket",
            interaction.channel.id,
        )

        await interaction.response.send_message(
            (
                f"✅ {interaction.channel.mention} 채널을 "
                "플리마켓 검색 채널로 설정했습니다."
            ),
            ephemeral=True,
        )

        guide_embed = discord.Embed(
            title="🏪 도동봇 플리마켓",
            description=(
                "판매하거나 구매할 물품을 검색할 수 있는 채널입니다.\n\n"
                "검색 기능과 플리마켓 홍보 등록 기능은 "
                "현재 준비 중입니다."
            ),
            color=discord.Color.green(),
        )

        guide_embed.set_footer(
            text="도동봇 플리마켓 테스트"
        )

        await interaction.channel.send(
            embed=guide_embed
        )

    @fleamarket_group.command(
        name="채널확인",
        description="현재 설정된 플리마켓 검색 채널을 확인합니다.",
    )
    async def check_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not self.is_owner(interaction):
            await interaction.response.send_message(
                "❌ 이 명령어는 도동봇 운영자만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        channel_id = get_channel_id(
            interaction.guild.id,
            "fleamarket",
        )

        if channel_id is None:
            await interaction.response.send_message(
                "❌ 현재 설정된 플리마켓 검색 채널이 없습니다.",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(
            channel_id
        )

        if channel is None:
            await interaction.response.send_message(
                "⚠️ 설정된 플리마켓 검색 채널을 찾을 수 없습니다.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            (
                "✅ 현재 플리마켓 검색 채널은 "
                f"{channel.mention}입니다."
            ),
            ephemeral=True,
        )

    @fleamarket_group.command(
        name="채널해제",
        description="현재 설정된 플리마켓 검색 채널을 해제합니다.",
    )
    async def remove_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not self.is_owner(interaction):
            await interaction.response.send_message(
                "❌ 이 명령어는 도동봇 운영자만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        removed = remove_channel_id(
            interaction.guild.id,
            "fleamarket",
        )

        if not removed:
            await interaction.response.send_message(
                "❌ 현재 설정된 플리마켓 검색 채널이 없습니다.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "✅ 플리마켓 검색 채널 설정을 해제했습니다.",
            ephemeral=True,
        )


async def setup(
    bot: commands.Bot,
) -> None:
    await bot.add_cog(
        FleaMarket(bot)
    )