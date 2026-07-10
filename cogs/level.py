import discord
from discord import app_commands
from discord.ext import commands


def total_xp_for_level(level: int) -> int:
    if level <= 16:
        return level * level + 6 * level
    elif level <= 31:
        return int(2.5 * level * level - 40.5 * level + 360)
    else:
        return int(4.5 * level * level - 162.5 * level + 2220)


def xp_to_level(total_xp: int):
    level = 0

    while total_xp_for_level(level + 1) <= total_xp:
        level += 1

    extra_xp = total_xp - total_xp_for_level(level)
    return level, extra_xp


class Level(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="경험치", description="바닐라 경험치를 레벨로 계산합니다.")
    @app_commands.describe(exp="계산할 총 경험치")
    async def level(self, interaction: discord.Interaction, exp: int):
        if exp < 0:
            await interaction.response.send_message("경험치는 0 이상이어야 합니다.")
            return

        level, extra_xp = xp_to_level(exp)

        await interaction.response.send_message(
            f"🎓 **바닐라 경험치**\n\n"
            f"{exp} EXP는\n"
            f"{level}레벨 + {extra_xp} EXP 입니다."
        )


async def setup(bot):
    await bot.add_cog(Level(bot))