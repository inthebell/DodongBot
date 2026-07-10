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
                "**🍳 요리 변동상점**\n"
                "`/요리 변동채널 설정`\n"
                "현재 채널을 요리 변동상점 채널로 설정합니다.\n"
                "`/요리 변동채널 확인`\n"
                "설정된 요리 변동상점 채널을 확인합니다.\n"
                "`/요리 변동채널 해제`\n"
                "요리 변동상점 채널 설정을 해제합니다.\n\n"
                "**🧪 연금 변동상점**\n"
                "`/연금 변동채널 설정`\n"
                "현재 채널을 연금 변동상점 채널로 설정합니다.\n"
                "`/연금 변동채널 확인`\n"
                "설정된 연금 변동상점 채널을 확인합니다.\n"
                "`/연금 변동채널 해제`\n"
                "연금 변동상점 채널 설정을 해제합니다.\n\n"
                "**🤝 동협 포인트 계산**\n"
                "`/동협`\n"
                "물의 결정 개수를 입력해 총 동협 포인트를 계산합니다."
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