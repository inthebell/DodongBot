import discord
from discord import app_commands
from discord.ext import commands


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="도움말", description="도동봇 명령어를 확인합니다.")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🏡 도동봇 도움말",
            description="도동마을 종합 관리봇입니다.",
            color=0xF4C26B
        )

        embed.add_field(
            name="⚡ 기본",
            value=(
                "`/핑`\n"
                "봇이 정상 작동하는지 확인합니다.\n\n"
                "`/도움말`\n"
                "명령어 목록을 확인합니다."
            ),
            inline=False
        )

        embed.add_field(
            name="📈 변동상점",
            value=(
                "`/요리`\n"
                "요리 변동상점을 분석합니다.\n\n"
                "`/연금`\n"
                "연금 변동상점을 분석합니다."
            ),
            inline=False
        )

        embed.add_field(
            name="🎓 계산",
            value=(
                "`/경험치`\n"
                "바닐라 경험치를 레벨로 계산합니다."
            ),
            inline=False
        )

        embed.set_footer(text="DodongBot v1.1.0")

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Help(bot))