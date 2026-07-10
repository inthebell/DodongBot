import discord
from discord import app_commands
from discord.ext import commands


POINTS = {
    "레어": 623,
    "유니크": 2048,
    "전설": 10074,
    "신화": 29966,
}


class Donghyeop(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="동협",
        description="물의 결정 개수를 입력해 총 동협 포인트를 계산합니다.",
    )
    @app_commands.rename(
        rare="레어",
        unique="유니크",
        legendary="전설",
        mythic="신화",
    )
    @app_commands.describe(
        rare="레어 물의 결정 개수를 입력해주세요.",
        unique="유니크 물의 결정 개수를 입력해주세요.",
        legendary="전설 물의 결정 개수를 입력해주세요.",
        mythic="신화 물의 결정 개수를 입력해주세요.",
    )
    async def donghyeop(
        self,
        interaction: discord.Interaction,
        rare: app_commands.Range[int, 0, 999999],
        unique: app_commands.Range[int, 0, 999999],
        legendary: app_commands.Range[int, 0, 999999],
        mythic: app_commands.Range[int, 0, 999999],
    ) -> None:
        counts = {
            "레어": rare,
            "유니크": unique,
            "전설": legendary,
            "신화": mythic,
        }

        total = sum(
            counts[grade] * POINTS[grade]
            for grade in POINTS
        )

        lines = ["🤝 **동협 포인트 계산**", ""]

        for grade in ["레어", "유니크", "전설", "신화"]:
            count = counts[grade]
            point = POINTS[grade]
            subtotal = count * point

            lines.append(
                f"• **{grade} 물의 결정** "
                f"{count:,}개 × {point:,}점 = **{subtotal:,}점**"
            )

        lines.append("")
        lines.append("━━━━━━━━━━━━━━")
        lines.append(
            f"현재 총 동협 포인트 : **{total:,}점**입니다."
        )

        await interaction.response.send_message(
            "\n".join(lines)
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Donghyeop(bot))