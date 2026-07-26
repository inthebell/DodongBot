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


class FleaMarket(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
    ):
        self.bot = bot

    fleamarket_group = app_commands.Group(
        name="플리마켓",
        description="플리마켓 홍보 및 검색 기능입니다.",
        guild_ids=[DODONG_GUILD_ID],
        default_permissions=discord.Permissions(
            administrator=True
        ),
    )

    def is_owner(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        return interaction.user.id == OWNER_ID

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