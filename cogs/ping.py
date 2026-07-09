import discord
from discord.ext import commands
from discord import app_commands


class Ping(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="핑", description="도동봇이 정상 작동하는지 확인합니다.")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "🏓 퐁!\n도동봇이 정상 작동 중입니다."
        )


async def setup(bot):
    await bot.add_cog(Ping(bot))
    