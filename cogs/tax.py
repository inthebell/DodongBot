import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks


DODONG_GUILD_ID = 1517850860322029618
NEW_TAX_GUILD_ID = 1385701565385408622
OWNER_ID = 478834154595811328

KST = timezone(timedelta(hours=9))

DATA_DIR = Path("data/tax")
TAX_SERVERS_FILE = Path("data/tax_servers.json")
LEGACY_DATA_FILE = Path("data/tax_data.json")

DEFAULT_ALLOWED_TAX_GUILDS = {
    DODONG_GUILD_ID,
    NEW_TAX_GUILD_ID,
}


def load_allowed_tax_guilds() -> set[int]:
    TAX_SERVERS_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not TAX_SERVERS_FILE.exists():
        guild_ids = sorted(DEFAULT_ALLOWED_TAX_GUILDS)
        save_allowed_tax_guilds(set(guild_ids))
        return set(guild_ids)

    try:
        with TAX_SERVERS_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)

        guild_ids = {
            int(guild_id)
            for guild_id in data.get("guilds", [])
        }

        guild_ids.add(DODONG_GUILD_ID)
        return guild_ids

    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return set(DEFAULT_ALLOWED_TAX_GUILDS)


def save_allowed_tax_guilds(guild_ids: set[int]) -> None:
    TAX_SERVERS_FILE.parent.mkdir(parents=True, exist_ok=True)

    with TAX_SERVERS_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            {"guilds": sorted(guild_ids)},
            file,
            ensure_ascii=False,
            indent=4,
        )


ALLOWED_TAX_GUILDS = load_allowed_tax_guilds()

DODONG_DEFAULT_TAX_AMOUNTS = {
    1: 20_000,
    2: 50_000,
    3: 70_000,
    4: 100_000,
}


def get_data_file(guild_id: int) -> Path:
    return DATA_DIR / f"{guild_id}.json"


def create_default_data(guild_id: int) -> dict:
    if guild_id == DODONG_GUILD_ID:
        tax_amounts = {
            str(tier): amount
            for tier, amount in DODONG_DEFAULT_TAX_AMOUNTS.items()
        }
    else:
        tax_amounts = {
            "1": None,
            "2": None,
            "3": None,
            "4": None,
        }

    return {
        "members": {},
        "payments": {},
        "tax_amounts": tax_amounts,
        "config": {
            "channel_id": None,
            "last_auto_notice_date": None,
        },
    }


def ensure_data_shape(data: dict, guild_id: int) -> dict:
    default_data = create_default_data(guild_id)

    if "members" not in data:
        data["members"] = {}

    if "payments" not in data:
        data["payments"] = {}

    if "tax_amounts" not in data:
        data["tax_amounts"] = default_data["tax_amounts"]

    for tier in ("1", "2", "3", "4"):
        if tier not in data["tax_amounts"]:
            data["tax_amounts"][tier] = default_data["tax_amounts"][tier]

    if "config" not in data:
        data["config"] = {}

    if "channel_id" not in data["config"]:
        data["config"]["channel_id"] = None

    if "last_auto_notice_date" not in data["config"]:
        data["config"]["last_auto_notice_date"] = None

    return data


def save_tax_data(guild_id: int, data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data_file = get_data_file(guild_id)

    with data_file.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=4,
        )


def migrate_legacy_dodong_data() -> None:
    dodong_file = get_data_file(DODONG_GUILD_ID)

    if dodong_file.exists() or not LEGACY_DATA_FILE.exists():
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(LEGACY_DATA_FILE, dodong_file)

    try:
        with dodong_file.open("r", encoding="utf-8") as file:
            data = json.load(file)

        data = ensure_data_shape(data, DODONG_GUILD_ID)
        save_tax_data(DODONG_GUILD_ID, data)

        print(
            "기존 도동마을 세금 데이터를 "
            f"{dodong_file} 파일로 이전했습니다."
        )
    except (json.JSONDecodeError, OSError) as error:
        print(f"기존 세금 데이터 이전 오류: {error}")


def load_tax_data(guild_id: int) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if guild_id == DODONG_GUILD_ID:
        migrate_legacy_dodong_data()

    data_file = get_data_file(guild_id)

    if not data_file.exists():
        data = create_default_data(guild_id)
        save_tax_data(guild_id, data)
        return data

    try:
        with data_file.open("r", encoding="utf-8") as file:
            data = json.load(file)

        return ensure_data_shape(data, guild_id)

    except (json.JSONDecodeError, OSError):
        return create_default_data(guild_id)


def get_tax_amount(data: dict, tier: int) -> int | None:
    amount = data.get("tax_amounts", {}).get(str(tier))

    if amount is None:
        return None

    return int(amount)


def get_week_dates(week_offset: int = 0):
    now = datetime.now(KST)
    monday = (
        now.date()
        - timedelta(days=now.weekday())
        + timedelta(weeks=week_offset)
    )
    sunday = monday + timedelta(days=6)

    return monday, sunday


def get_week_key(week_offset: int = 0) -> str:
    monday, sunday = get_week_dates(week_offset)
    return f"{monday.isoformat()}_{sunday.isoformat()}"


def get_week_text(week_offset: int = 0) -> str:
    monday, sunday = get_week_dates(week_offset)

    return (
        f"{monday.strftime('%Y-%m-%d')} ~ "
        f"{sunday.strftime('%Y-%m-%d')}"
    )


def get_sorted_members(members: dict):
    return sorted(
        members.items(),
        key=lambda item: (
            -item[1].get("tier", 0),
            item[1].get("game_name", "").lower(),
        ),
    )


def group_members_by_tier(
    data: dict,
    payments: dict,
    paid: bool,
) -> tuple[str, int]:
    members = data["members"]

    groups = {
        4: [],
        3: [],
        2: [],
        1: [],
    }

    count = 0

    for member_id, member_data in get_sorted_members(members):
        is_paid = member_id in payments

        if is_paid != paid:
            continue

        tier = member_data.get("tier", 0)
        game_name = member_data.get("game_name", "알 수 없음")
        amount = get_tax_amount(data, tier) or 0

        if paid:
            payment_info = payments[member_id]
            paid_amount = payment_info.get("amount", amount)
            prepaid_weeks = payment_info.get("prepaid_weeks", 1)
            week_offset = payment_info.get("week_offset", 0)

            if prepaid_weeks >= 2:
                week_text = f" · {week_offset + 1}/{prepaid_weeks}주"
            else:
                week_text = ""

            line = (
                f"<@{member_id}> · `{game_name}` · "
                f"{paid_amount:,}냥{week_text}"
            )
        else:
            line = (
                f"<@{member_id}> · `{game_name}` · "
                f"{amount:,}냥"
            )

        if tier in groups:
            groups[tier].append(line)

        count += 1

    sections = []

    for tier in (4, 3, 2, 1):
        if not groups[tier]:
            continue

        icon = "🔴" if not paid else "🟢"
        lines = "\n".join(
            f"└ {line}" for line in groups[tier]
        )

        sections.append(
            f"{icon} **{tier}차**\n{lines}"
        )

    if not sections:
        if paid:
            return "아직 납부한 마을원이 없습니다.", 0

        return "모든 마을원이 납부했습니다.", 0

    return "\n\n".join(sections), count


def create_tax_status_embed(
    data: dict,
    guild_name: str,
) -> discord.Embed:
    members = data["members"]
    week_key = get_week_key()
    payments = data["payments"].get(week_key, {})

    unpaid_text, unpaid_count = group_members_by_tier(
        data,
        payments,
        paid=False,
    )

    paid_text, paid_count = group_members_by_tier(
        data,
        payments,
        paid=True,
    )

    embed = discord.Embed(
        title=f"📋 {guild_name} 주간 세금 현황",
        description=(
            f"납부 기간: **{get_week_text()}**\n"
            f"전체 마을원: **{len(members)}명**"
        ),
        color=discord.Color.blue(),
        timestamp=datetime.now(KST),
    )

    embed.add_field(
        name=f"❌ 미납 ({unpaid_count}명)",
        value=unpaid_text,
        inline=False,
    )

    embed.add_field(
        name=f"✅ 납부 완료 ({paid_count}명)",
        value=paid_text,
        inline=False,
    )

    if unpaid_count == 0:
        embed.set_footer(
            text="🎉 이번 주 세금 납부가 모두 완료되었습니다!"
        )
    else:
        embed.set_footer(
            text="아직 납부하지 않은 마을원은 기간 내 납부 부탁드립니다."
        )

    return embed


TAX_GUILD_OBJECTS = [
    discord.Object(id=guild_id)
    for guild_id in ALLOWED_TAX_GUILDS
]


@app_commands.guilds(*TAX_GUILD_OBJECTS)
class Tax(
    commands.GroupCog,
    group_name="세금",
    group_description="마을 세금 관리 명령어입니다.",
):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        super().__init__()
        self.daily_tax_notice.start()

    def cog_unload(self):
        self.daily_tax_notice.cancel()

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

        if interaction.guild.id not in ALLOWED_TAX_GUILDS:
            await interaction.response.send_message(
                "❌ 세금 시스템 사용 권한이 없는 서버입니다.",
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

    async def register_tax_group_for_guild(
        self,
        guild_id: int,
    ) -> None:
        guild_object = discord.Object(id=guild_id)
        group = self.__cog_app_commands_group__

        self.bot.tree.add_command(
            group,
            guild=guild_object,
            override=True,
        )

        await self.bot.tree.sync(guild=guild_object)

    async def unregister_tax_group_from_guild(
        self,
        guild_id: int,
    ) -> None:
        guild_object = discord.Object(id=guild_id)

        self.bot.tree.remove_command(
            self.__cog_app_commands_group__.name,
            guild=guild_object,
            type=discord.AppCommandType.chat_input,
        )

        await self.bot.tree.sync(guild=guild_object)

    @app_commands.command(
        name="서버추가",
        description="세금 시스템을 사용할 서버를 추가합니다.",
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

        if guild_id in ALLOWED_TAX_GUILDS:
            await interaction.response.send_message(
                f"⚠️ **{guild.name}** 서버는 이미 등록되어 있습니다.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        ALLOWED_TAX_GUILDS.add(guild_id)
        save_allowed_tax_guilds(ALLOWED_TAX_GUILDS)
        load_tax_data(guild_id)

        try:
            await self.register_tax_group_for_guild(guild_id)
        except Exception as error:
            ALLOWED_TAX_GUILDS.discard(guild_id)
            save_allowed_tax_guilds(ALLOWED_TAX_GUILDS)

            await interaction.followup.send(
                f"❌ 세금 명령어 등록에 실패했습니다.\n`{error}`",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            (
                "✅ 세금 시스템 서버 추가가 완료되었습니다.\n\n"
                f"**서버:** {guild.name}\n"
                f"**서버 ID:** `{guild_id}`\n\n"
                "해당 서버 관리자는 `/세금 금액설정`부터 "
                "진행해 주세요."
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="서버삭제",
        description="서버의 세금 시스템 사용 권한을 해제합니다.",
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

        guild = self.bot.get_guild(guild_id)
        guild_name = guild.name if guild else "알 수 없는 서버"

        await interaction.response.defer(ephemeral=True)

        ALLOWED_TAX_GUILDS.discard(guild_id)
        save_allowed_tax_guilds(ALLOWED_TAX_GUILDS)

        try:
            await self.unregister_tax_group_from_guild(guild_id)
        except Exception as error:
            ALLOWED_TAX_GUILDS.add(guild_id)
            save_allowed_tax_guilds(ALLOWED_TAX_GUILDS)

            await interaction.followup.send(
                f"❌ 세금 명령어 해제에 실패했습니다.\n`{error}`",
                ephemeral=True,
            )
            return

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
        name="서버목록",
        description="세금 시스템 사용이 허용된 서버를 확인합니다.",
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
            timestamp=datetime.now(KST),
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="금액설정",
        description="해당 서버의 차수별 주간 세금을 설정합니다.",
    )
    @app_commands.describe(
        차수="금액을 설정할 차수",
        금액="해당 차수의 주간 세금",
    )
    @app_commands.choices(
        차수=[
            app_commands.Choice(name="1차", value=1),
            app_commands.Choice(name="2차", value=2),
            app_commands.Choice(name="3차", value=3),
            app_commands.Choice(name="4차", value=4),
        ]
    )
    async def tax_amount_setting(
        self,
        interaction: discord.Interaction,
        차수: app_commands.Choice[int],
        금액: app_commands.Range[int, 0, 2_000_000_000],
    ):
        if not await self.check_admin(interaction):
            return

        guild_id = interaction.guild.id
        data = load_tax_data(guild_id)

        tier = 차수.value
        old_amount = get_tax_amount(data, tier)
        new_amount = int(금액)

        data["tax_amounts"][str(tier)] = new_amount

        for member_data in data["members"].values():
            if member_data.get("tier") == tier:
                member_data["tax_amount"] = new_amount

        save_tax_data(guild_id, data)

        old_amount_text = (
            f"{old_amount:,}냥"
            if old_amount is not None
            else "미설정"
        )

        embed = discord.Embed(
            title="⚙️ 세금 금액 설정 완료",
            color=discord.Color.green(),
            timestamp=datetime.now(KST),
        )

        embed.add_field(
            name="🏷️ 차수",
            value=f"{tier}차",
            inline=True,
        )
        embed.add_field(
            name="기존 금액",
            value=old_amount_text,
            inline=True,
        )
        embed.add_field(
            name="새 금액",
            value=f"{new_amount:,}냥",
            inline=True,
        )

        embed.set_footer(
            text="기존에 등록된 해당 차수 마을원에게도 새 금액이 적용됩니다."
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="금액조회",
        description="현재 서버의 차수별 세금 금액을 확인합니다.",
    )
    async def tax_amount_status(
        self,
        interaction: discord.Interaction,
    ):
        if not await self.check_admin(interaction):
            return

        data = load_tax_data(interaction.guild.id)
        lines = []

        for tier in (4, 3, 2, 1):
            amount = get_tax_amount(data, tier)
            amount_text = (
                f"{amount:,}냥"
                if amount is not None
                else "미설정"
            )
            lines.append(f"**{tier}차** : {amount_text}")

        embed = discord.Embed(
            title=f"💰 {interaction.guild.name} 세금 금액",
            description="\n".join(lines),
            color=discord.Color.blurple(),
            timestamp=datetime.now(KST),
        )

        await interaction.response.send_message(embed=embed)

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
            app_commands.Choice(name="1차", value=1),
            app_commands.Choice(name="2차", value=2),
            app_commands.Choice(name="3차", value=3),
            app_commands.Choice(name="4차", value=4),
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

        guild_id = interaction.guild.id
        data = load_tax_data(guild_id)

        game_name = 게임닉.strip()

        if not game_name:
            await interaction.response.send_message(
                "❌ 게임 닉네임을 입력해 주세요.",
                ephemeral=True,
            )
            return

        member_id = str(대상.id)
        tier = 차수.value
        amount = get_tax_amount(data, tier)

        if amount is None:
            await interaction.response.send_message(
                (
                    f"❌ {tier}차 세금 금액이 아직 설정되지 않았습니다.\n"
                    "먼저 `/세금 금액설정`을 사용해 주세요."
                ),
                ephemeral=True,
            )
            return

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

        save_tax_data(guild_id, data)

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
            text="✅ 마을원 정보가 저장되었습니다."
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="납부",
        description="마을원의 세금 납부를 기록합니다.",
    )
    @app_commands.describe(
        대상="세금을 납부한 마을원",
        주수="납부할 주수 (선택하지 않으면 1주)",
    )
    @app_commands.choices(
        주수=[
            app_commands.Choice(name="1주", value=1),
            app_commands.Choice(name="2주", value=2),
            app_commands.Choice(name="3주", value=3),
            app_commands.Choice(name="4주", value=4),
        ]
    )
    async def tax_payment(
        self,
        interaction: discord.Interaction,
        대상: discord.Member,
        주수: app_commands.Choice[int] | None = None,
    ):
        if not await self.check_admin(interaction):
            return

        guild_id = interaction.guild.id
        data = load_tax_data(guild_id)

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

        selected_weeks = 주수.value if 주수 else 1
        duplicate_weeks = []

        for week_offset in range(selected_weeks):
            week_key = get_week_key(week_offset)
            week_payments = data["payments"].get(week_key, {})

            if member_id in week_payments:
                duplicate_weeks.append(
                    get_week_text(week_offset)
                )

        if duplicate_weeks:
            duplicate_text = "\n".join(
                f"• {week_text}"
                for week_text in duplicate_weeks
            )

            await interaction.response.send_message(
                (
                    f"⚠️ {대상.mention}님의 납부 기록이 "
                    "이미 있는 주가 있습니다.\n\n"
                    f"{duplicate_text}\n\n"
                    "중복 기록을 막기 위해 저장하지 않았습니다."
                ),
                ephemeral=True,
            )
            return

        tier = member_data["tier"]
        weekly_amount = get_tax_amount(data, tier)

        if weekly_amount is None:
            await interaction.response.send_message(
                (
                    f"❌ {tier}차 세금 금액이 설정되어 있지 않습니다.\n"
                    "먼저 `/세금 금액설정`을 사용해 주세요."
                ),
                ephemeral=True,
            )
            return

        paid_at = datetime.now(KST).isoformat()

        for week_offset in range(selected_weeks):
            week_key = get_week_key(week_offset)

            if week_key not in data["payments"]:
                data["payments"][week_key] = {}

            data["payments"][week_key][member_id] = {
                "amount": weekly_amount,
                "paid_at": paid_at,
                "recorded_by": interaction.user.id,
                "prepaid_weeks": selected_weeks,
                "week_offset": week_offset,
            }

        save_tax_data(guild_id, data)

        total_amount = weekly_amount * selected_weeks

        embed = discord.Embed(
            title="✅ 세금 납부 완료",
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
            value=f"{tier}차",
            inline=True,
        )
        embed.add_field(
            name="💰 주간 세금",
            value=f"{weekly_amount:,}냥",
            inline=True,
        )
        embed.add_field(
            name="📅 납부 주수",
            value=f"{selected_weeks}주",
            inline=True,
        )

        if selected_weeks >= 2:
            embed.add_field(
                name="💵 총 납부 금액",
                value=f"{total_amount:,}냥",
                inline=True,
            )

        embed.set_footer(
            text=(
                "이번 주 세금 납부가 기록되었습니다."
                if selected_weeks == 1
                else (
                    f"이번 주부터 {selected_weeks}주간 "
                    "세금 납부가 기록되었습니다."
                )
            )
        )

        await interaction.response.send_message(embed=embed)

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

        data = load_tax_data(interaction.guild.id)

        if not data["members"]:
            await interaction.response.send_message(
                "❌ 등록된 마을원이 없습니다.",
                ephemeral=True,
            )
            return

        embed = create_tax_status_embed(
            data,
            interaction.guild.name,
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="취소",
        description="마을원의 세금 납부 기록을 취소합니다.",
    )
    @app_commands.describe(
        대상="납부 기록을 취소할 마을원",
        주수="취소할 주수 (선택하지 않으면 1주)",
    )
    @app_commands.choices(
        주수=[
            app_commands.Choice(name="1주", value=1),
            app_commands.Choice(name="2주", value=2),
            app_commands.Choice(name="3주", value=3),
            app_commands.Choice(name="4주", value=4),
        ]
    )
    async def tax_cancel(
        self,
        interaction: discord.Interaction,
        대상: discord.Member,
        주수: app_commands.Choice[int] | None = None,
    ):
        if not await self.check_admin(interaction):
            return

        guild_id = interaction.guild.id
        data = load_tax_data(guild_id)

        member_id = str(대상.id)
        selected_weeks = 주수.value if 주수 else 1

        cancelled_weeks = []
        missing_weeks = []

        for week_offset in range(selected_weeks):
            week_key = get_week_key(week_offset)
            week_text = get_week_text(week_offset)
            payments = data["payments"].get(week_key, {})

            if member_id in payments:
                del payments[member_id]
                cancelled_weeks.append(week_text)
            else:
                missing_weeks.append(week_text)

        if not cancelled_weeks:
            await interaction.response.send_message(
                (
                    f"❌ {대상.mention}님의 선택한 기간에 "
                    "세금 납부 기록이 없습니다."
                ),
                ephemeral=True,
            )
            return

        save_tax_data(guild_id, data)

        cancelled_text = "\n".join(
            f"• {week_text}"
            for week_text in cancelled_weeks
        )

        embed = discord.Embed(
            title="↩️ 세금 납부 기록 취소",
            description=(
                f"{대상.mention}님의 세금 납부 기록을 취소했습니다."
            ),
            color=discord.Color.orange(),
            timestamp=datetime.now(KST),
        )

        embed.add_field(
            name="📅 취소된 기간",
            value=cancelled_text,
            inline=False,
        )
        embed.add_field(
            name="🗓️ 취소 주수",
            value=f"{len(cancelled_weeks)}주",
            inline=True,
        )

        if missing_weeks:
            missing_text = "\n".join(
                f"• {week_text}"
                for week_text in missing_weeks
            )

            embed.add_field(
                name="⚠️ 기록이 없던 기간",
                value=missing_text,
                inline=False,
            )

        embed.set_footer(
            text="취소된 주차는 다시 미납 상태로 표시됩니다."
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="명단",
        description="세금 명단에 등록된 전체 마을원을 확인합니다.",
    )
    async def tax_member_list(
        self,
        interaction: discord.Interaction,
    ):
        if not await self.check_admin(interaction):
            return

        data = load_tax_data(interaction.guild.id)
        members = data["members"]

        if not members:
            await interaction.response.send_message(
                "❌ 등록된 마을원이 없습니다.",
                ephemeral=True,
            )
            return

        groups = {
            4: [],
            3: [],
            2: [],
            1: [],
        }

        for member_id, member_data in get_sorted_members(members):
            tier = member_data.get("tier", 0)
            game_name = member_data.get(
                "game_name",
                "알 수 없음",
            )
            amount = get_tax_amount(data, tier) or 0

            if tier in groups:
                groups[tier].append(
                    (
                        f"<@{member_id}> · `{game_name}` · "
                        f"{amount:,}냥"
                    )
                )

        embed = discord.Embed(
            title=f"🏡 {interaction.guild.name} 세금 명단",
            description=f"전체 마을원: **{len(members)}명**",
            color=discord.Color.blurple(),
            timestamp=datetime.now(KST),
        )

        for tier in (4, 3, 2, 1):
            lines = groups[tier]
            tier_amount = get_tax_amount(data, tier)
            amount_text = (
                f"{tier_amount:,}냥"
                if tier_amount is not None
                else "미설정"
            )

            if not lines:
                value = "등록된 마을원이 없습니다."
            else:
                value = "\n".join(
                    f"• {line}" for line in lines
                )

            embed.add_field(
                name=(
                    f"{tier}차 · "
                    f"{amount_text} "
                    f"({len(lines)}명)"
                ),
                value=value,
                inline=False,
            )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="수정",
        description="등록된 마을원의 게임 닉네임 또는 차수를 수정합니다.",
    )
    @app_commands.describe(
        대상="정보를 수정할 마을원",
        게임닉="새 게임 닉네임",
        차수="새 차수",
    )
    @app_commands.choices(
        차수=[
            app_commands.Choice(name="1차", value=1),
            app_commands.Choice(name="2차", value=2),
            app_commands.Choice(name="3차", value=3),
            app_commands.Choice(name="4차", value=4),
        ]
    )
    async def tax_edit(
        self,
        interaction: discord.Interaction,
        대상: discord.Member,
        게임닉: str,
        차수: app_commands.Choice[int],
    ):
        if not await self.check_admin(interaction):
            return

        guild_id = interaction.guild.id
        data = load_tax_data(guild_id)
        member_id = str(대상.id)

        if member_id not in data["members"]:
            await interaction.response.send_message(
                (
                    f"❌ {대상.mention}님은 등록된 "
                    "마을원이 아닙니다."
                ),
                ephemeral=True,
            )
            return

        old_data = data["members"][member_id]
        old_game_name = old_data.get("game_name", "알 수 없음")
        old_tier = old_data.get("tier", 0)

        new_game_name = 게임닉.strip()
        new_tier = 차수.value
        new_amount = get_tax_amount(data, new_tier)

        if new_amount is None:
            await interaction.response.send_message(
                (
                    f"❌ {new_tier}차 세금 금액이 아직 설정되지 않았습니다.\n"
                    "먼저 `/세금 금액설정`을 사용해 주세요."
                ),
                ephemeral=True,
            )
            return

        data["members"][member_id].update(
            {
                "discord_name": str(대상),
                "display_name": 대상.display_name,
                "game_name": new_game_name,
                "tier": new_tier,
                "tax_amount": new_amount,
                "updated_at": datetime.now(KST).isoformat(),
                "updated_by": interaction.user.id,
            }
        )

        save_tax_data(guild_id, data)

        embed = discord.Embed(
            title="✏️ 마을원 정보 수정 완료",
            color=discord.Color.gold(),
            timestamp=datetime.now(KST),
        )

        embed.add_field(
            name="👤 대상",
            value=대상.mention,
            inline=False,
        )
        embed.add_field(
            name="🎮 게임 닉네임",
            value=f"`{old_game_name}` → `{new_game_name}`",
            inline=False,
        )
        embed.add_field(
            name="🏷️ 차수",
            value=f"{old_tier}차 → {new_tier}차",
            inline=True,
        )
        embed.add_field(
            name="💰 주간 세금",
            value=f"{new_amount:,}냥",
            inline=True,
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="삭제",
        description="마을원을 세금 명단에서 삭제합니다.",
    )
    @app_commands.describe(
        대상="세금 명단에서 삭제할 마을원",
    )
    async def tax_delete(
        self,
        interaction: discord.Interaction,
        대상: discord.Member,
    ):
        if not await self.check_admin(interaction):
            return

        guild_id = interaction.guild.id
        data = load_tax_data(guild_id)
        member_id = str(대상.id)

        member_data = data["members"].get(member_id)

        if member_data is None:
            await interaction.response.send_message(
                (
                    f"❌ {대상.mention}님은 등록된 "
                    "마을원이 아닙니다."
                ),
                ephemeral=True,
            )
            return

        game_name = member_data.get(
            "game_name",
            "알 수 없음",
        )

        del data["members"][member_id]

        for week_payments in data["payments"].values():
            week_payments.pop(member_id, None)

        save_tax_data(guild_id, data)

        embed = discord.Embed(
            title="🗑️ 마을원 삭제 완료",
            description=(
                f"{대상.mention} · `{game_name}`님을\n"
                "세금 명단에서 삭제했습니다."
            ),
            color=discord.Color.red(),
            timestamp=datetime.now(KST),
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="채널",
        description="매일 00시 세금 현황이 올라올 채널을 설정합니다.",
    )
    @app_commands.describe(
        채널="자동 세금 현황을 전송할 채널",
    )
    async def tax_channel(
        self,
        interaction: discord.Interaction,
        채널: discord.TextChannel,
    ):
        if not await self.check_admin(interaction):
            return

        guild_id = interaction.guild.id
        data = load_tax_data(guild_id)
        data["config"]["channel_id"] = 채널.id
        save_tax_data(guild_id, data)

        embed = discord.Embed(
            title="⚙️ 세금 자동 공지 채널 설정",
            description=(
                f"매일 한국 시간 **00:00**에\n"
                f"{채널.mention} 채널로 세금 현황을 전송합니다."
            ),
            color=discord.Color.green(),
            timestamp=datetime.now(KST),
        )

        await interaction.response.send_message(embed=embed)

    @tasks.loop(minutes=1)
    async def daily_tax_notice(self):
        now = datetime.now(KST)

        if now.hour != 0 or now.minute != 0:
            return

        today_text = now.date().isoformat()

        for guild_id in ALLOWED_TAX_GUILDS:
            guild = self.bot.get_guild(guild_id)

            if guild is None:
                continue

            data = load_tax_data(guild_id)
            channel_id = data["config"].get("channel_id")

            if not channel_id:
                continue

            last_notice_date = data["config"].get(
                "last_auto_notice_date"
            )

            if last_notice_date == today_text:
                continue

            channel = guild.get_channel(channel_id)

            if not isinstance(channel, discord.TextChannel):
                continue

            if not data["members"]:
                continue

            embed = create_tax_status_embed(
                data,
                guild.name,
            )

            try:
                await channel.send(
                    content=(
                        "📢 아직 이번 주 세금을 납부하지 않은 "
                        "마을원은 기간 내 납부 부탁드립니다!"
                    ),
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions.none(),
                )

                data["config"]["last_auto_notice_date"] = today_text
                save_tax_data(guild_id, data)

            except discord.HTTPException as error:
                print(
                    f"{guild.name} 세금 자동 공지 전송 오류: "
                    f"{error}"
                )

    @daily_tax_notice.before_loop
    async def before_daily_tax_notice(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Tax(bot))