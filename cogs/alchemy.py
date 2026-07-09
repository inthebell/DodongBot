import re
import discord
from discord import app_commands
from discord.ext import commands

RUNE_RANGE = {
    "화염저항": (180, 270),
    "호흡": (207, 311),
    "신속": (228, 342),
    "성급": (402, 603),
    "힘": (405, 608),
}


def get_status(price: int, low: int, high: int):
    mid = (low + high) / 2
    high_point = low + (high - low) * 0.9

    if price >= high_point:
        return "고점"

    if price >= mid:
        return "추천"

    return "저점"


def parse_alchemy(text: str):

    result = {
        "고점": [],
        "추천": [],
        "저점": []
    }

    pattern = r"\[(.*?)\]\s*\|\s*(\d+)\s*→\s*(\d+)"

    for raw_name, old_price, new_price in re.findall(pattern, text):

        # 세로선 통일
        name = raw_name.replace("ㅣ", "|")

        # 룬 앞부분 제거 (띄어쓰기 전부 대응)
        name = (
            name.replace("룬 |", "")
                .replace("룬|", "")
                .replace("룬  |", "")
                .replace("룬 ㅣ", "")
                .replace("룬ㅣ", "")
                .strip()
        )

        # 어색한 결정 제외
        if "어색한 결정" in name:
            continue

        if name not in RUNE_RANGE:
            print("인식 실패:", name)   # 디버깅용
            continue

        low, high = RUNE_RANGE[name]

        status = get_status(int(new_price), low, high)

        result[status].append(
            f"🧪 **룬 | {name}** - {new_price}원"
        )

    return result


def build_text(result):

    text = "🧪 **연금 변동상점**\n"

    text += "\n🔥 고점\n\n"

    if result["고점"]:
        text += "\n".join(result["고점"])
    else:
        text += "없음"

    text += "\n\n━━━━━━━━━━━━\n"

    text += "\n⭐ 추천\n\n"

    if result["추천"]:
        text += "\n".join(result["추천"])
    else:
        text += "없음"

    text += "\n\n━━━━━━━━━━━━\n"

    text += "\n📉 저점\n\n"

    if result["저점"]:
        text += "\n".join(result["저점"])
    else:
        text += "없음"

    text += "\n\n━━━━━━━━━━━━\n"

    text += "\n📌 변동 시세\n\n"

    for name, (low, high) in RUNE_RANGE.items():
        text += f"룬 | {name}  {low}~{high}원\n"

    return text


class AlchemyModal(discord.ui.Modal, title="연금 변동상점 분석"):

    content = discord.ui.TextInput(
        label="연금 변동 내용을 붙여넣어 주세요.",
        style=discord.TextStyle.paragraph,
        max_length=4000
    )

    async def on_submit(self, interaction: discord.Interaction):

        result = parse_alchemy(str(self.content))

        await interaction.response.send_message(
            build_text(result)
        )


class Alchemy(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="연금",
        description="연금 변동상점을 분석합니다."
    )
    async def alchemy(self, interaction: discord.Interaction):

        await interaction.response.send_modal(
            AlchemyModal()
        )


async def setup(bot):
    await bot.add_cog(Alchemy(bot))