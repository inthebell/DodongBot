import re
import discord
from discord import app_commands
from discord.ext import commands


FOOD_TIERS = {
    "아스파라거스 샐러드": 1,
    "갈릭 포테이토 콩피": 1,
    "레몬 당근 라페": 1,
    "어니언 포테이토 그라탱": 1,
    "고로케": 1,

    "갈릭 아스파라거스 피클": 2,
    "시트러스 어니언 스튜": 2,
    "어니언 감자조림": 2,
    "아스파라거스 라페": 2,

    "파프리카 비프 스튜": 3,
    "피치 레몬 치킨": 3,
    "허브 램 플래터": 3,
    "스파이시 갈릭 포크": 3,

    "비프 라구 파이": 4,
    "복숭아 치킨 타르트": 4,
    "키슈 파이": 4,
    "갈릭 포크 크로켓": 4,

    "크리미 파프리카 비프플레이트": 5,
    "시트러스 피치 치킨램": 5,
    "그린 허브 램플": 5,
    "스파이시 포크라이스": 5,
}

PRICE_RANGE = {
    1: (48, 62),
    2: (69, 90),
    3: (120, 156),
    4: (191, 248),
    5: (209, 272),
}


def get_status(price: int, low: int, high: int) -> str:
    mid = (low + high) / 2
    high_point = low + (high - low) * 0.9

    if price >= high_point:
        return "고점"
    if price >= mid:
        return "추천"
    return "저점"


def is_normal_food(raw_name: str) -> bool:
    return "🩶" not in raw_name and "🌟" not in raw_name


def parse_cooking(text: str):
    results = {"고점": {}, "추천": {}}

    pattern = r"\[(.*?)\]\s*\|\s*(\d+)\s*→\s*(\d+)"

    for raw_name, old_price, current_price in re.findall(pattern, text):
        if not is_normal_food(raw_name):
            continue

        name = raw_name.strip()
        price = int(current_price)

        tier = FOOD_TIERS.get(name)
        if not tier:
            continue

        low, high = PRICE_RANGE[tier]
        status = get_status(price, low, high)

        if status == "저점":
            continue

        results[status].setdefault((tier, low, high), []).append(
              f"🍳 **{name}** - {price}원"
        )

    return results


def build_result_text(results):
    parts = ["🍳 **요리 변동상점**"]

    for status, title in [("고점", "🔥 고점"), ("추천", "⭐ 추천")]:

        if title != "🔥 고점":
            parts.append("\n━━━━━━━━━━━━━━")

        parts.append(f"\n{title}")

        if not results.get(status):
            parts.append("없음")
            continue

        for (tier, low, high), items in sorted(results[status].items()):
            parts.append(f"\n【{tier}차】 ({low}~{high}원)")
            parts.extend(items)

    parts.append("\n━━━━━━━━━━━━━━")
    parts.append("\n※ 중간값 이하의 음식은 표시되지 않습니다.")
    parts.append("※ 추천은 변동 시세의 중간값 이상, 고점은 상위 10% 구간을 기준으로 선정됩니다.")
    return "\n".join(parts)


class CookingModal(discord.ui.Modal, title="요리 변동상점 분석"):
    content = discord.ui.TextInput(
        label="요리 변동상점 내용을 붙여넣어 주세요",
        style=discord.TextStyle.paragraph,
        placeholder="🍳[아스파라거스 샐러드] | 53 → 57",
        required=True,
        max_length=4000,
    )

    async def on_submit(self, interaction: discord.Interaction):
        results = parse_cooking(str(self.content))
        message = build_result_text(results)
        await interaction.response.send_message(message)


class Cooking(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="요리", description="요리 변동상점을 분석합니다.")
    async def cooking(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CookingModal())


async def setup(bot):
    await bot.add_cog(Cooking(bot))