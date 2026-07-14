import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands


DODONG_GUILD_ID = 1517850860322029618

KST = timezone(timedelta(hours=9))

DATA_FILE = Path("data/tax_data.json")

TAX_AMOUNTS = {
    1: 20_000,
    2: 50_000,
    3: 70_000,
    4: 100_000,
}


def create_default_data() -> dict:
    return {
        "members": {},
        "payments": {},
    }


def load_tax_data() -> dict:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not DATA_FILE.exists():
        data = create_default_data()
        save_tax_data(data)
        return data

    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if "members" not in data:
            data["members"] = {}

        if "payments" not in data:
            data["payments"] = {}

        return data

    except (json.JSONDecodeError, OSError):
        return create_default_data()


def save_tax_data(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=4,
        )


def get_week_dates():
    now = datetime.now(KST)
    monday = now.date() - timedelta(days=now.weekday())
    sunday = monday + timedelta(days=6)

    return monday, sunday


def get_week_key() -> str:
    monday, sunday = get_week_dates()

    return f"{monday.isoformat()}_{sunday.isoformat()}"


def get_week_text() -> str:
    monday, sunday = get_week_dates()

    return (
        f"{monday.strftime('%Y-%m-%d')} ~ "
        f"{sunday.strftime('%Y-%m-%d')}"
    )


@app_commands.guilds(discord.Object(id=DODONG_GUILD_ID))
class Tax(
    commands.GroupCog,
    group_name="세금",
    group_description="도동마을 세금 관리 명령어입니다.",
):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        super().__init__()

    async def check_admin(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ 서버에서만 사용할 수 있는 명령어입니다.",
                ephemeral=True,
            )
            return False

        if interaction.guild.id != DODONG_GUILD_ID:
            await interaction.response.send_message(
                "❌ 도동마을 서버 전용 명령어입니다.",
                ephemeral=True,
            )
            return False

        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "❌ 사용자 정보를 확인할 수 없습니다.",
                ephemeral=True,
            )
            return False

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ 관리자만 사용할 수 있는 명령어입니다.",
                ephemeral=True,
            )
            return False

        return True

    @app_commands.command(
        name="등록",
        description="마을원의 게임 닉네임과 차수를 등록합니다.",
    )
    @app_commands.describe(
        대상="등록할 마을원",
        게임닉="마인크래프트 게임 닉네임",
        차수="마을원의 차수",
    )
    @app_commands.choices(
        차수=[
            app_commands.Choice(
                name="1차 - 20,000냥",
                value=1,
            ),
            app_commands.Choice(
                name="2차 - 50,000냥",
                value=2,
            ),
            app_commands.Choice(
                name="3차 - 70,000냥",
                value=3,
            ),
            app_commands.Choice(
                name="4차 - 100,000냥",
                value=4,
            ),
        ]
    )
    async def tax_register(
        self,
        interaction: discord.Interaction,
        대상: discord.Member,
        게임닉: str,
        차수: app_commands.Choice[int],
    ):
        if not await self.check_admin(interaction):
            return

        game_name = 게임닉.strip()

        if not game_name:
            await interaction.response.send_message(
                "❌ 게임 닉네임을 입력해 주세요.",
                ephemeral=True,
            )
            return

        data = load_tax_data()

        member_id = str(대상.id)
        tier = 차수.value
        amount = TAX_AMOUNTS[tier]

        already_registered = member_id in data["members"]

        data["members"][member_id] = {
            "discord_name": str(대상),
            "display_name": 대상.display_name,
            "game_name": game_name,
            "tier": tier,
            "tax_amount": amount,
            "registered_at": datetime.now(KST).isoformat(),
            "registered_by": interaction.user.id,
        }

        save_tax_data(data)

        title = (
            "🏡 마을원 정보 수정 완료"
            if already_registered
            else "🏡 마을원 등록 완료"
        )

        embed = discord.Embed(
            title=title,
            color=discord.Color.green(),
            timestamp=datetime.now(KST),
        )

        embed.add_field(
            name="👤 대상",
            value=대상.mention,
            inline=False,
        )

        embed.add_field(
            name="🎮 게임 닉네임",
            value=f"`{game_name}`",
            inline=True,
        )

        embed.add_field(
            name="🏷️ 차수",
            value=f"{tier}차",
            inline=True,
        )

        embed.add_field(
            name="💰 주간 세금",
            value=f"{amount:,}냥",
            inline=True,
        )

        embed.set_footer(
            text="마을원 세금 정보가 저장되었습니다."
        )

        await interaction.response.send_message(
            embed=embed,
        )

    @app_commands.command(
        name="납부",
        description="마을원의 이번 주 세금 납부를 기록합니다.",
    )
    @app_commands.describe(
        대상="세금을 납부한 마을원",
    )
    async def tax_payment(
        self,
        interaction: discord.Interaction,
        대상: discord.Member,
    ):
        if not await self.check_admin(interaction):
            return

        data = load_tax_data()

        member_id = str(대상.id)
        member_data = data["members"].get(member_id)

        if member_data is None:
            await interaction.response.send_message(
                (
                    f"❌ {대상.mention}님은 세금 명단에 "
                    "등록되어 있지 않습니다.\n"
                    "먼저 `/세금 등록`을 사용해 주세요."
                ),
                ephemeral=True,
            )
            return

        week_key = get_week_key()

        if week_key not in data["payments"]:
            data["payments"][week_key] = {}

        existing_payment = data["payments"][week_key].get(
            member_id
        )

        if existing_payment is not None:
            existing_amount = existing_payment.get(
                "amount",
                member_data["tax_amount"],
            )

            await interaction.response.send_message(
                (
                    f"⚠️ {대상.mention}님은 이번 주 세금이 "
                    "이미 기록되어 있습니다.\n"
                    f"납부 금액: **{existing_amount:,}냥**\n\n"
                    "잘못 기록했다면 `/세금 취소`를 사용해 주세요."
                ),
                ephemeral=True,
            )
            return

        amount = member_data["tax_amount"]

        data["payments"][week_key][member_id] = {
            "amount": amount,
            "paid_at": datetime.now(KST).isoformat(),
            "recorded_by": interaction.user.id,
        }

        save_tax_data(data)

        embed = discord.Embed(
            title="📥 세금 납부 확인",
            color=discord.Color.green(),
            timestamp=datetime.now(KST),
        )

        embed.add_field(
            name="👤 대상",
            value=대상.mention,
            inline=False,
        )

        embed.add_field(
            name="🎮 게임 닉네임",
            value=f"`{member_data['game_name']}`",
            inline=True,
        )

        embed.add_field(
            name="🏷️ 차수",
            value=f"{member_data['tier']}차",
            inline=True,
        )

        embed.add_field(
            name="💰 금액",
            value=f"{amount:,}냥",
            inline=True,
        )

        embed.set_footer(
            text="✅ 이번 주 세금 납부가 기록되었습니다."
        )

        await interaction.response.send_message(
            embed=embed,
        )

    @app_commands.command(
        name="조회",
        description="이번 주 세금 납부 현황을 조회합니다.",
    )
    async def tax_status(
        self,
        interaction: discord.Interaction,
    ):
        if not await self.check_admin(interaction):
            return

        data = load_tax_data()
        members = data["members"]

        if not members:
            await interaction.response.send_message(
                "❌ 등록된 마을원이 없습니다.",
                ephemeral=True,
            )
            return

        week_key = get_week_key()
        payments = data["payments"].get(week_key, {})

        paid_lines = []
        unpaid_lines = []

        sorted_members = sorted(
            members.items(),
            key=lambda item: (
                item[1].get("tier", 0),
                item[1].get("game_name", "").lower(),
            ),
            reverse=True,
        )

        for member_id, member_data in sorted_members:
            mention = f"<@{member_id}>"
            game_name = member_data.get(
                "game_name",
                "알 수 없음",
            )
            tier = member_data.get("tier", 0)

            if member_id in payments:
                amount = payments[member_id].get(
                    "amount",
                    member_data.get("tax_amount", 0),
                )

                paid_lines.append(
                    (
                        f"✅ {mention}\n"
                        f"└ `{game_name}` · {tier}차 · "
                        f"{amount:,}냥"
                    )
                )
            else:
                amount = member_data.get(
                    "tax_amount",
                    TAX_AMOUNTS.get(tier, 0),
                )

                unpaid_lines.append(
                    (
                        f"❌ {mention}\n"
                        f"└ `{game_name}` · {tier}차 · "
                        f"{amount:,}냥"
                    )
                )

        paid_text = (
            "\n".join(paid_lines)
            if paid_lines
            else "아직 납부한 마을원이 없습니다."
        )

        unpaid_text = (
            "\n".join(unpaid_lines)
            if unpaid_lines
            else "모든 마을원이 납부했습니다."
        )

        embed = discord.Embed(
            title="📋 도동마을 주간 세금 현황",
            description=(
                f"납부 기간: **{get_week_text()}**\n"
                f"전체 마을원: **{len(members)}명**"
            ),
            color=discord.Color.blue(),
            timestamp=datetime.now(KST),
        )

        embed.add_field(
            name=f"✅ 납부 완료 ({len(paid_lines)}명)",
            value=paid_text,
            inline=False,
        )

        embed.add_field(
            name=f"❌ 미납 ({len(unpaid_lines)}명)",
            value=unpaid_text,
            inline=False,
        )

        if not unpaid_lines:
            embed.set_footer(
                text="🎉 이번 주 세금 납부가 모두 완료되었습니다!"
            )
        else:
            embed.set_footer(
                text="아직 납부하지 않은 마을원은 기간 내 납부 부탁드립니다."
            )

        await interaction.response.send_message(
            embed=embed,
        )

    @app_commands.command(
        name="취소",
        description="마을원의 이번 주 세금 납부 기록을 취소합니다.",
    )
    @app_commands.describe(
        대상="납부 기록을 취소할 마을원",
    )
    async def tax_cancel(
        self,
        interaction: discord.Interaction,
        대상: discord.Member,
    ):
        if not await self.check_admin(interaction):
            return

        data = load_tax_data()

        member_id = str(대상.id)
        week_key = get_week_key()
        payments = data["payments"].get(week_key, {})

        if member_id not in payments:
            await interaction.response.send_message(
                (
                    f"❌ {대상.mention}님의 이번 주 "
                    "세금 납부 기록이 없습니다."
                ),
                ephemeral=True,
            )
            return

        del payments[member_id]

        save_tax_data(data)

        embed = discord.Embed(
            title="↩️ 세금 납부 기록 취소",
            description=(
                f"{대상.mention}님의 이번 주 세금 납부 기록을 "
                "취소했습니다."
            ),
            color=discord.Color.orange(),
            timestamp=datetime.now(KST),
        )

        embed.set_footer(
            text="해당 마을원은 다시 미납 상태로 표시됩니다."
        )

        await interaction.response.send_message(
            embed=embed,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Tax(bot))