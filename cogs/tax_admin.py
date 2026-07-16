import discord
from discord import app_commands
from discord.ext import commands

from cogs.tax import (
    ALLOWED_TAX_GUILDS,
    DODONG_GUILD_ID,
    OWNER_ID,
    load_tax_data,
    save_allowed_tax_guilds,
)

class TaxAdmin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def check_owner(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message(
                "❌ 도동봇 오너만 사용할 수 있는 명령어입니다.",
                ephemeral=True,
            )
            return False

        return True

    def get_tax_cog(self):
        return self.bot.get_cog("Tax")

    @app_commands.command(
        name="세금서버추가",
        description="세금 시스템을 사용할 서버를 추가합니다.",
    )
    @app_commands.guilds(
        discord.Object(id=DODONG_GUILD_ID),
    )
    @app_commands.describe(
        서버아이디="세금 시스템을 활성화할 디스코드 서버 ID",
    )
    async def tax_server_add(
        self,
        interaction: discord.Interaction,
        서버아이디: str,
    ):
        if not await self.check_owner(interaction):
            return

        try:
            guild_id = int(서버아이디.strip())
        except ValueError:
            await interaction.response.send_message(
                "❌ 서버 ID는 숫자로 입력해 주세요.",
                ephemeral=True,
            )
            return

        guild = self.bot.get_guild(guild_id)

        if guild is None:
            await interaction.response.send_message(
                (
                    "❌ 도동봇이 해당 서버에 들어가 있지 않거나 "
                    "서버 ID가 올바르지 않습니다."
                ),
                ephemeral=True,
            )
            return

        tax_cog = self.get_tax_cog()

        if tax_cog is None:
            await interaction.response.send_message(
                "❌ 세금 기능을 불러오지 못했습니다.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        already_registered = guild_id in ALLOWED_TAX_GUILDS

        if not already_registered:
            ALLOWED_TAX_GUILDS.add(guild_id)
            save_allowed_tax_guilds(ALLOWED_TAX_GUILDS)
            load_tax_data(guild_id)

        try:
            await tax_cog.register_tax_group_for_guild(guild_id)
        except Exception as error:
            if not already_registered:
                ALLOWED_TAX_GUILDS.discard(guild_id)
                save_allowed_tax_guilds(ALLOWED_TAX_GUILDS)

            await interaction.followup.send(
                (
                    "❌ 세금 명령어 등록에 실패했습니다.\n"
                    f"`{error}`"
                ),
                ephemeral=True,
            )
            return

        if already_registered:
            message = (
                f"🔄 **{guild.name}** 서버는 이미 등록되어 있습니다.\n\n"
                "세금 명령어를 다시 동기화했습니다."
            )
        else:
            message = (
                "✅ 세금 시스템 서버 추가가 완료되었습니다.\n\n"
                f"**서버:** {guild.name}\n"
                f"**서버 ID:** `{guild_id}`\n\n"
                "해당 서버 관리자는 `/세금 금액설정`부터 "
                "진행해 주세요."
            )

        await interaction.followup.send(
            message,
            ephemeral=True,
        )

    @app_commands.command(
        name="세금서버삭제",
        description="서버의 세금 시스템 사용 권한을 해제합니다.",
    )
    @app_commands.guilds(
        discord.Object(id=DODONG_GUILD_ID),
    )
    @app_commands.describe(
        서버아이디="세금 시스템을 비활성화할 디스코드 서버 ID",
    )
    async def tax_server_remove(
        self,
        interaction: discord.Interaction,
        서버아이디: str,
    ):
        if not await self.check_owner(interaction):
            return

        try:
            guild_id = int(서버아이디.strip())
        except ValueError:
            await interaction.response.send_message(
                "❌ 서버 ID는 숫자로 입력해 주세요.",
                ephemeral=True,
            )
            return

        if guild_id == DODONG_GUILD_ID:
            await interaction.response.send_message(
                "❌ 도동마을 서버는 목록에서 삭제할 수 없습니다.",
                ephemeral=True,
            )
            return

        if guild_id not in ALLOWED_TAX_GUILDS:
            await interaction.response.send_message(
                "❌ 등록되어 있지 않은 서버입니다.",
                ephemeral=True,
            )
            return

        tax_cog = self.get_tax_cog()

        if tax_cog is None:
            await interaction.response.send_message(
                "❌ 세금 기능을 불러오지 못했습니다.",
                ephemeral=True,
            )
            return

        guild = self.bot.get_guild(guild_id)
        guild_name = guild.name if guild else "알 수 없는 서버"

        await interaction.response.defer(ephemeral=True)

        try:
            await tax_cog.unregister_tax_group_from_guild(guild_id)
        except Exception as error:
            await interaction.followup.send(
                (
                    "❌ 세금 명령어 해제에 실패했습니다.\n"
                    f"`{error}`"
                ),
                ephemeral=True,
            )
            return

        ALLOWED_TAX_GUILDS.discard(guild_id)
        save_allowed_tax_guilds(ALLOWED_TAX_GUILDS)

        await interaction.followup.send(
            (
                "✅ 세금 시스템 사용 권한을 해제했습니다.\n\n"
                f"**서버:** {guild_name}\n"
                f"**서버 ID:** `{guild_id}`\n\n"
                "기존 세금 데이터 파일은 삭제하지 않고 보관합니다."
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="세금서버목록",
        description="세금 시스템 사용이 허용된 서버를 확인합니다.",
    )
    @app_commands.guilds(
        discord.Object(id=DODONG_GUILD_ID),
    )
    async def tax_server_list(
        self,
        interaction: discord.Interaction,
    ):
        if not await self.check_owner(interaction):
            return

        lines = []

        for guild_id in sorted(ALLOWED_TAX_GUILDS):
            guild = self.bot.get_guild(guild_id)
            guild_name = guild.name if guild else "알 수 없는 서버"

            lines.append(
                f"🏡 **{guild_name}**\n└ `{guild_id}`"
            )

        embed = discord.Embed(
            title="📋 세금 시스템 사용 서버",
            description=(
                "\n\n".join(lines)
                if lines
                else "등록된 서버가 없습니다."
            ),
            color=discord.Color.blurple(),
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(TaxAdmin(bot))