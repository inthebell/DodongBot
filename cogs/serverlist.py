import discord
from discord import app_commands
from discord.ext import commands


OWNER_ID = 478834154595811328
GUILD_ID = 1517850860322029618


class ServerList(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="서버목록",
        description="도동봇이 들어가 있는 서버 목록을 확인합니다."
    )
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def server_list(self, interaction: discord.Interaction):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message(
                "❌ 이 명령어를 사용할 권한이 없습니다.",
                ephemeral=True
            )
            return

        guilds = sorted(
            self.bot.guilds,
            key=lambda guild: guild.member_count or 0,
            reverse=True
        )

        lines = [
            "📊 **도동봇 서버 목록**",
            "",
            f"총 서버 : **{len(guilds)}개**",
            ""
        ]

        for guild in guilds:
            member_count = guild.member_count or 0

            lines.append(f"◉ **{guild.name}**")
            lines.append(f"👥 **{member_count:,}명**")
            lines.append("")

        await interaction.response.send_message(
            "\n".join(lines),
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(ServerList(bot))