import sqlite3
from datetime import datetime, timedelta, timezone

import discord

from cogs.fleamarket_db import (
    approve_ad,
    create_ad,
    delete_ad,
    get_ad,
    get_user_ad,
    has_existing_ad,
    reject_ad,
    set_approval_message,
    update_pending_ad,
    update_user_ad_for_review,
)
OWNER_ID = 478834154595811328
FLEAMARKET_APPROVAL_CHANNEL_ID = 1531285321902198805


MARKET_DB_PATH = "market.db"
MAX_ITEM_SELECTION = 5
MAX_ITEM_RESULTS = 25


def normalize_market_search(value: str) -> str:
    return (
        value.lower()
        .replace(" ", "")
        .replace("ㅣ", "")
        .replace("|", "")
        .replace("[", "")
        .replace("]", "")
    )


def display_item_name(value: str) -> str:
    return value.replace("ㅣ", " | ")


def search_market_items(
    search_term: str,
    *,
    limit: int = MAX_ITEM_RESULTS,
) -> list[str]:
    normalized_term = normalize_market_search(search_term)

    if len(normalized_term) < 2:
        return []

    try:
        with sqlite3.connect(MARKET_DB_PATH) as connection:
            rows = connection.execute(
                """
                SELECT item_name, COUNT(*) AS trade_count
                FROM trades
                WHERE item_name IS NOT NULL
                  AND TRIM(item_name) != ''
                GROUP BY item_name
                """
            ).fetchall()
    except sqlite3.Error:
        return []

    matched: list[tuple[int, int, str]] = []

    for item_name, trade_count in rows:
        normalized_name = normalize_market_search(item_name)

        if normalized_term not in normalized_name:
            continue

        if normalized_name == normalized_term:
            priority = 0
        elif normalized_name.startswith(normalized_term):
            priority = 1
        else:
            priority = 2

        matched.append(
            (
                priority,
                -int(trade_count),
                str(item_name),
            )
        )

    matched.sort(
        key=lambda item: (
            item[0],
            item[1],
            display_item_name(item[2]),
        )
    )

    return [
        item_name
        for _, _, item_name in matched[:limit]
    ]


def market_emoji(market_type: str) -> str:
    return "🟢" if market_type == "판매" else "🔴"


def market_color(market_type: str) -> discord.Color:
    if market_type == "판매":
        return discord.Color.green()
    return discord.Color.red()


def normalize_single_line(value: str) -> str:
    return " ".join(value.split())


def parse_categories(
    value: str,
) -> tuple[list[str] | None, str | None]:
    categories = [
        category.strip()
        for category in value.replace("，", ",").split(",")
        if category.strip()
    ]

    categories = list(dict.fromkeys(categories))

    if not categories:
        return None, "❌ 분류를 1개 이상 입력해주세요."

    if len(categories) > 5:
        return None, "❌ 분류는 최대 5개까지 입력할 수 있습니다."

    if any(len(category) > 10 for category in categories):
        return None, "❌ 각 분류는 최대 10자까지 입력할 수 있습니다."

    return categories, None


def parse_keywords(
    value: str,
) -> tuple[list[str] | None, str | None]:
    keywords = [
        keyword.strip()
        for keyword in value.replace("，", ",").split(",")
        if keyword.strip()
    ]

    keywords = list(dict.fromkeys(keywords))

    if not keywords:
        return None, "❌ 세부 키워드를 1개 이상 입력해주세요."

    if len(keywords) > 5:
        return None, "❌ 세부 키워드는 최대 5개까지 입력할 수 있습니다."

    if any(len(keyword) > 100 for keyword in keywords):
        return None, "❌ 각 세부 키워드는 최대 100자까지 입력할 수 있습니다."

    return keywords, None


KST = timezone(timedelta(hours=9))


def format_expiration(expires_at: str | None) -> str:
    if not expires_at:
        return "승인 후 3일"

    try:
        value = datetime.fromisoformat(expires_at)
        return value.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return expires_at


def format_remaining_time(expires_at: str | None) -> str:
    if not expires_at:
        return "승인 후 3일"

    try:
        expiration = datetime.fromisoformat(expires_at)

        if expiration.tzinfo is None:
            expiration = expiration.replace(tzinfo=KST)

        remaining = expiration - datetime.now(KST)
        total_seconds = int(remaining.total_seconds())

        if total_seconds <= 0:
            return "만료됨"

        days, remainder = divmod(total_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes = remainder // 60

        parts: list[str] = []

        if days > 0:
            parts.append(f"{days}일")

        if hours > 0 or days > 0:
            parts.append(f"{hours}시간")

        parts.append(f"{minutes}분")
        return " ".join(parts)

    except (TypeError, ValueError):
        return "확인 불가"


def build_approval_embed(
    ad: dict,
    *,
    applicant: discord.abc.User | None = None,
) -> discord.Embed:
    type_emoji = market_emoji(ad["type"])
    categories = " · ".join(
        item for item in ad["category"].split(",") if item
    )
    keywords = " · ".join(
        item for item in ad["keywords"].split(",") if item
    )

    if applicant is None:
        applicant_text = f"<@{ad['user_id']}>"
    else:
        applicant_text = (
            f"{applicant.mention}\n"
            f"{applicant} (`{applicant.id}`)"
        )

    is_revision = int(ad.get("revision_count") or 0) > 0

    embed = discord.Embed(
        title=(
            "✏️ 플리마켓 홍보 수정 재승인"
            if is_revision
            else "📋 플리마켓 홍보 신청"
        ),
        description=(
            (
                "수정된 홍보입니다. 재승인 전까지 검색 결과에서 제외됩니다.\n"
                "재승인되어도 최초 승인 기준 만료 시각은 연장되지 않습니다."
            )
            if is_revision
            else "무료 홍보 신청입니다. 승인 후 3일간 검색 결과에 노출됩니다."
        ),
        color=market_color(ad["type"]),
    )

    embed.add_field(
        name="신청 번호",
        value=f"`{ad['id']}`",
        inline=True,
    )
    embed.add_field(
        name="거래 구분",
        value=f"{type_emoji} {ad['type']}",
        inline=True,
    )
    embed.add_field(
        name="신청자",
        value=applicant_text,
        inline=False,
    )
    embed.add_field(
        name="분류",
        value=categories,
        inline=False,
    )
    embed.add_field(
        name="세부 키워드",
        value=keywords,
        inline=False,
    )
    embed.add_field(
        name="검색 결과 미리보기",
        value=(
            f"{type_emoji} {ad['type']}\n"
            f"📢 {ad['description']}\n"
            f"📍 {ad['waypoint']}"
        ),
        inline=False,
    )
    embed.add_field(
        name="노출 기간",
        value=(
            (
                f"최초 승인 기준 만료 유지\n"
                f"만료 예정: {format_expiration(ad.get('expires_at'))}\n"
                f"남은 기간: {format_remaining_time(ad.get('expires_at'))}"
            )
            if is_revision and ad.get("expires_at")
            else "최초 승인 시점부터 3일간"
        ),
        inline=False,
    )
    embed.set_footer(text="현재 상태: 승인 대기")
    return embed


async def get_user(
    interaction: discord.Interaction,
    user_id: int,
) -> discord.User | None:
    user = interaction.client.get_user(user_id)

    if user is not None:
        return user

    try:
        return await interaction.client.fetch_user(user_id)
    except discord.HTTPException:
        return None


async def notify_applicant(
    interaction: discord.Interaction,
    ad: dict,
    message: str,
) -> None:
    user = await get_user(interaction, ad["user_id"])
    if user is None:
        return

    try:
        await user.send(message)
    except discord.HTTPException:
        pass


async def get_approval_channel(
    interaction: discord.Interaction,
) -> discord.TextChannel | None:
    channel = interaction.client.get_channel(
        FLEAMARKET_APPROVAL_CHANNEL_ID
    )

    if channel is None:
        try:
            channel = await interaction.client.fetch_channel(
                FLEAMARKET_APPROVAL_CHANNEL_ID
            )
        except (
            discord.Forbidden,
            discord.NotFound,
            discord.HTTPException,
        ):
            return None

    if not isinstance(channel, discord.TextChannel):
        return None

    return channel


async def send_new_approval_message(
    interaction: discord.Interaction,
    ad: dict,
) -> bool:
    approval_channel = await get_approval_channel(interaction)

    if approval_channel is None:
        return False

    try:
        approval_message = await approval_channel.send(
            embed=build_approval_embed(
                ad,
                applicant=interaction.user,
            ),
            view=FleaMarketApprovalView(ad["id"]),
        )
    except discord.HTTPException:
        return False

    set_approval_message(
        ad["id"],
        approval_channel.id,
        approval_message.id,
    )
    return True


async def update_existing_approval_message(
    interaction: discord.Interaction,
    ad: dict,
) -> bool:
    channel_id = ad.get("approval_channel_id")
    message_id = ad.get("approval_message_id")

    if not channel_id or not message_id:
        return False

    channel = interaction.client.get_channel(channel_id)

    if not isinstance(channel, discord.TextChannel):
        return False

    try:
        message = await channel.fetch_message(message_id)
        await message.edit(
            embed=build_approval_embed(ad),
            view=FleaMarketApprovalView(ad["id"]),
        )
        return True
    except discord.HTTPException:
        return False


class FleaMarketOwnerEditModal(discord.ui.Modal):
    def __init__(self, ad_id: int):
        ad = get_ad(ad_id)
        if ad is None:
            raise ValueError("수정할 신청을 찾을 수 없습니다.")

        super().__init__(title=f"플리마켓 신청 #{ad_id} 수정")
        self.ad_id = ad_id

        self.category = discord.ui.TextInput(
            label="분류 (쉼표로 최대 5개)",
            default=ad["category"].replace(",", ", "),
            required=True,
            max_length=60,
        )
        self.keywords = discord.ui.TextInput(
            label="세부 검색 키워드",
            default=ad["keywords"].replace(",", ", "),
            required=True,
            max_length=60,
        )
        self.description = discord.ui.TextInput(
            label="홍보 문구",
            default=ad["description"],
            required=True,
            max_length=60,
        )
        self.waypoint = discord.ui.TextInput(
            label="이정표",
            default=ad["waypoint"],
            required=True,
            max_length=50,
        )

        self.add_item(self.category)
        self.add_item(self.keywords)
        self.add_item(self.description)
        self.add_item(self.waypoint)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message(
                "❌ 도동봇 운영자만 수정할 수 있습니다.",
                ephemeral=True,
            )
            return

        categories, category_error = parse_categories(
            self.category.value
        )
        if category_error:
            await interaction.response.send_message(
                category_error,
                ephemeral=True,
            )
            return

        keywords, keyword_error = parse_keywords(
            self.keywords.value
        )
        if keyword_error:
            await interaction.response.send_message(
                keyword_error,
                ephemeral=True,
            )
            return

        assert categories is not None
        assert keywords is not None

        updated = update_pending_ad(
            ad_id=self.ad_id,
            category=",".join(categories),
            keywords=",".join(keywords),
            description=normalize_single_line(
                self.description.value
            ),
            waypoint=normalize_single_line(
                self.waypoint.value
            ),
        )

        if not updated:
            await interaction.response.send_message(
                "❌ 이미 처리되었거나 존재하지 않는 신청입니다.",
                ephemeral=True,
            )
            return

        ad = get_ad(self.ad_id)
        if ad is None:
            await interaction.response.send_message(
                "❌ 수정된 신청을 다시 불러오지 못했습니다.",
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            embed=build_approval_embed(ad),
            view=FleaMarketApprovalView(self.ad_id),
        )
        await interaction.followup.send(
            "✏️ 신청 내용을 수정했습니다. 확인 후 승인해주세요.",
            ephemeral=True,
        )


class FleaMarketUserEditModal(discord.ui.Modal):
    def __init__(
        self,
        ad_id: int,
        user_id: int,
    ):
        ad = get_ad(ad_id)
        if ad is None:
            raise ValueError("수정할 홍보를 찾을 수 없습니다.")

        super().__init__(title=f"내 플리마켓 홍보 #{ad_id} 수정")
        self.ad_id = ad_id
        self.user_id = user_id

        self.category = discord.ui.TextInput(
            label="분류 (쉼표로 최대 5개)",
            default=ad["category"].replace(",", ", "),
            required=True,
            max_length=60,
        )
        self.keywords = discord.ui.TextInput(
            label="세부 검색 키워드",
            default=ad["keywords"].replace(",", ", "),
            required=True,
            max_length=60,
        )
        self.description = discord.ui.TextInput(
            label="홍보 문구",
            default=ad["description"],
            required=True,
            max_length=60,
        )
        self.waypoint = discord.ui.TextInput(
            label="이정표",
            default=ad["waypoint"],
            required=True,
            max_length=50,
        )

        self.add_item(self.category)
        self.add_item(self.keywords)
        self.add_item(self.description)
        self.add_item(self.waypoint)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ 본인의 홍보만 수정할 수 있습니다.",
                ephemeral=True,
            )
            return

        categories, category_error = parse_categories(
            self.category.value
        )
        if category_error:
            await interaction.response.send_message(
                category_error,
                ephemeral=True,
            )
            return

        keywords, keyword_error = parse_keywords(
            self.keywords.value
        )
        if keyword_error:
            await interaction.response.send_message(
                keyword_error,
                ephemeral=True,
            )
            return

        assert categories is not None
        assert keywords is not None

        updated, was_active = update_user_ad_for_review(
            ad_id=self.ad_id,
            user_id=self.user_id,
            category=",".join(categories),
            keywords=",".join(keywords),
            description=normalize_single_line(
                self.description.value
            ),
            waypoint=normalize_single_line(
                self.waypoint.value
            ),
        )

        if not updated:
            await interaction.response.send_message(
                "❌ 수정할 수 있는 홍보를 찾지 못했습니다.",
                ephemeral=True,
            )
            return

        ad = get_ad(self.ad_id)
        if ad is None:
            await interaction.response.send_message(
                "❌ 수정된 홍보를 불러오지 못했습니다.",
                ephemeral=True,
            )
            return

        if was_active:
            approval_sent = await send_new_approval_message(
                interaction,
                ad,
            )
        else:
            approval_sent = await update_existing_approval_message(
                interaction,
                ad,
            )
            if not approval_sent:
                approval_sent = await send_new_approval_message(
                    interaction,
                    ad,
                )

        if not approval_sent:
            await interaction.response.send_message(
                (
                    "⚠️ 내용은 수정되었지만 승인 채널에 "
                    "재승인 신청서를 보내지 못했습니다.\n"
                    "운영자에게 문의해주세요."
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            (
                "✅ 홍보 내용이 수정되었습니다.\n"
                "수정된 홍보는 검색에서 내려갔으며, "
                "운영자 재승인 후 기존 만료 시각까지 다시 노출됩니다.\n"
                f"남은 기간: {format_remaining_time(ad.get('expires_at'))}"
                if was_active
                else
                "✅ 승인 대기 중인 신청 내용을 수정했습니다.\n"
                "운영자 승인 후 3일간 노출됩니다."
            ),
            ephemeral=True,
        )


class FleaMarketApprovalView(discord.ui.View):
    def __init__(self, ad_id: int):
        super().__init__(timeout=None)
        self.ad_id = ad_id

        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.custom_id = (
                    f"fleamarket:{child.custom_id}:{ad_id}"
                )

    async def owner_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == OWNER_ID:
            return True

        await interaction.response.send_message(
            "❌ 도동봇 운영자만 처리할 수 있습니다.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(
        label="승인",
        emoji="✅",
        style=discord.ButtonStyle.success,
        custom_id="approve",
    )
    async def approve(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not await self.owner_check(interaction):
            return

        ad = get_ad(self.ad_id)

        if ad is None or ad["status"] != "pending":
            await interaction.response.send_message(
                "❌ 이미 처리되었거나 존재하지 않는 신청입니다.",
                ephemeral=True,
            )
            return

        if not approve_ad(
            ad_id=self.ad_id,
            reviewer_id=interaction.user.id,
        ):
            await interaction.response.send_message(
                "❌ 신청 상태를 변경하지 못했습니다.",
                ephemeral=True,
            )
            return

        approved_ad = get_ad(self.ad_id)
        if approved_ad is None:
            await interaction.response.send_message(
                "❌ 승인된 홍보를 다시 불러오지 못했습니다.",
                ephemeral=True,
            )
            return

        is_revision = int(
            approved_ad.get("revision_count") or 0
        ) > 0

        embed = build_approval_embed(approved_ad)
        embed.title = (
            "✅ 플리마켓 홍보 재승인 완료"
            if is_revision
            else "✅ 플리마켓 홍보 승인 완료"
        )
        embed.description = (
            (
                "수정된 홍보가 다시 검색 결과에 노출됩니다.\n"
                "노출 기간은 연장되지 않으며 최초 승인 기준 만료 시각을 유지합니다."
            )
            if is_revision
            else "최초 승인 시점부터 3일간 검색 결과에 노출됩니다."
        )
        embed.color = discord.Color.green()
        embed.set_footer(
            text=(
                f"승인 완료 · 만료 "
                f"{format_expiration(approved_ad['expires_at'])} · "
                f"처리자: {interaction.user}"
            )
        )

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            embed=embed,
            view=self,
        )

        await notify_applicant(
            interaction,
            approved_ad,
            (
                (
                    f"✅ 플리마켓 {approved_ad['type']} 홍보 수정이 재승인되었습니다.\n"
                    "최초 승인 기준 만료 시각까지 다시 검색 결과에 노출됩니다.\n"
                    f"만료 예정: {format_expiration(approved_ad['expires_at'])}\n"
                    f"남은 기간: {format_remaining_time(approved_ad['expires_at'])}"
                )
                if is_revision
                else
                (
                    f"✅ 플리마켓 {approved_ad['type']} 홍보가 승인되었습니다.\n"
                    "최초 승인 시점부터 3일간 검색 결과에 노출됩니다.\n"
                    f"만료 예정: {format_expiration(approved_ad['expires_at'])}"
                )
            ),
        )

    @discord.ui.button(
        label="수정",
        emoji="✏️",
        style=discord.ButtonStyle.primary,
        custom_id="edit",
    )
    async def edit(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not await self.owner_check(interaction):
            return

        ad = get_ad(self.ad_id)
        if ad is None or ad["status"] != "pending":
            await interaction.response.send_message(
                "❌ 이미 처리되었거나 존재하지 않는 신청입니다.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            FleaMarketOwnerEditModal(self.ad_id)
        )

    @discord.ui.button(
        label="반려",
        emoji="❌",
        style=discord.ButtonStyle.danger,
        custom_id="reject",
    )
    async def reject(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not await self.owner_check(interaction):
            return

        ad = get_ad(self.ad_id)
        if ad is None or ad["status"] != "pending":
            await interaction.response.send_message(
                "❌ 이미 처리되었거나 존재하지 않는 신청입니다.",
                ephemeral=True,
            )
            return

        if not reject_ad(
            ad_id=self.ad_id,
            reviewer_id=interaction.user.id,
        ):
            await interaction.response.send_message(
                "❌ 신청 상태를 변경하지 못했습니다.",
                ephemeral=True,
            )
            return

        embed = build_approval_embed(ad)
        embed.title = "❌ 플리마켓 홍보 반려"
        embed.color = discord.Color.red()
        embed.set_footer(
            text=f"반려 완료 · 처리자: {interaction.user}"
        )

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            embed=embed,
            view=self,
        )

        await notify_applicant(
            interaction,
            ad,
            (
                f"❌ 플리마켓 {ad['type']} 홍보 신청이 반려되었습니다.\n"
                "내용을 확인한 뒤 다시 신청해주세요."
            ),
        )




class FleaMarketRegisterModal(discord.ui.Modal):
    def __init__(
        self,
        market_type: str,
        selected_items: list[str],
        search_terms: list[str],
    ):
        super().__init__(
            title=f"플리마켓 {market_type} 홍보 등록"
        )
        self.market_type = market_type
        self.selected_items = selected_items

        category_default = ", ".join(
            dict.fromkeys(
                normalize_single_line(term)
                for term in search_terms
                if normalize_single_line(term)
            )
        )[:60]

        self.category = discord.ui.TextInput(
            label="분류 (쉼표로 최대 5개)",
            placeholder="예) 금별요리, 작물, 광물",
            default=category_default or None,
            required=True,
            max_length=60,
        )
        self.description = discord.ui.TextInput(
            label="홍보 문구",
            placeholder="예) 선택한 아이템 판매합니다.",
            required=True,
            max_length=60,
        )
        self.waypoint = discord.ui.TextInput(
            label="이정표",
            placeholder="예) /이정표 도동마켓",
            required=True,
            max_length=50,
        )

        self.add_item(self.category)
        self.add_item(self.description)
        self.add_item(self.waypoint)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        categories, category_error = parse_categories(
            self.category.value
        )
        if category_error:
            await interaction.response.send_message(
                category_error,
                ephemeral=True,
            )
            return

        if not self.selected_items:
            await interaction.response.send_message(
                "❌ 선택된 아이템이 없습니다. 다시 등록해주세요.",
                ephemeral=True,
            )
            return

        if len(self.selected_items) > MAX_ITEM_SELECTION:
            await interaction.response.send_message(
                f"❌ 아이템은 최대 {MAX_ITEM_SELECTION}개까지 선택할 수 있습니다.",
                ephemeral=True,
            )
            return

        assert categories is not None

        if (
            interaction.user.id != OWNER_ID
            and has_existing_ad(
                interaction.guild.id,
                interaction.user.id,
                self.market_type,
            )
        ):
            await interaction.response.send_message(
                (
                    f"❌ 이미 {self.market_type} 홍보가 "
                    "신청 또는 등록되어 있습니다.\n\n"
                    "`/플리마켓 내홍보`, `/플리마켓 홍보수정`, "
                    "`/플리마켓 홍보삭제`를 이용해주세요."
                ),
                ephemeral=True,
            )
            return

        category = ",".join(categories)
        description = normalize_single_line(
            self.description.value
        )
        waypoint = normalize_single_line(
            self.waypoint.value
        )
        stored_keywords = ",".join(self.selected_items)

        try:
            ad_id = create_ad(
                guild_id=interaction.guild.id,
                user_id=interaction.user.id,
                market_type=self.market_type,
                category=category,
                keywords=stored_keywords,
                description=description,
                waypoint=waypoint,
            )
        except sqlite3.Error:
            await interaction.response.send_message(
                "❌ 홍보 신청을 저장하는 중 오류가 발생했습니다.",
                ephemeral=True,
            )
            return

        approval_channel = await get_approval_channel(
            interaction
        )

        if approval_channel is None:
            delete_ad(ad_id)
            await interaction.response.send_message(
                (
                    "❌ 중앙 플리마켓 승인 채널을 찾을 수 없습니다.\n"
                    "도동봇 운영자에게 문의해주세요."
                ),
                ephemeral=True,
            )
            return

        ad = get_ad(ad_id)
        if ad is None:
            delete_ad(ad_id)
            await interaction.response.send_message(
                "❌ 저장된 신청 내용을 불러오지 못했습니다.",
                ephemeral=True,
            )
            return

        try:
            approval_message = await approval_channel.send(
                embed=build_approval_embed(
                    ad,
                    applicant=interaction.user,
                ),
                view=FleaMarketApprovalView(ad_id),
            )
        except discord.HTTPException:
            delete_ad(ad_id)
            await interaction.response.send_message(
                "❌ 승인 채널에 신청서를 전송하지 못했습니다.",
                ephemeral=True,
            )
            return

        set_approval_message(
            ad_id,
            approval_channel.id,
            approval_message.id,
        )

        type_emoji = market_emoji(self.market_type)
        selected_text = "\n".join(
            f"• {display_item_name(item)}"
            for item in self.selected_items
        )

        embed = discord.Embed(
            title="✅ 플리마켓 홍보 신청 완료",
            description=(
                "홍보 신청이 정상적으로 접수되었습니다.\n"
                "현재 홍보 등록은 무료이며, 운영자 승인 후 "
                "3일간 검색 결과에 노출됩니다."
            ),
            color=market_color(self.market_type),
        )
        embed.add_field(
            name="거래 구분",
            value=f"{type_emoji} {self.market_type}",
            inline=False,
        )
        embed.add_field(
            name="분류",
            value=" · ".join(categories),
            inline=False,
        )
        embed.add_field(
            name="선택한 아이템",
            value=selected_text,
            inline=False,
        )
        embed.add_field(
            name="검색 결과 미리보기",
            value=(
                f"{type_emoji} {self.market_type}\n"
                f"📢 {description}\n"
                f"📍 {waypoint}"
            ),
            inline=False,
        )
        embed.add_field(
            name="노출 기간",
            value="승인 시점부터 3일간",
            inline=False,
        )
        embed.set_footer(
            text=f"신청 번호 #{ad_id} · 현재 상태: 승인 대기"
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )


def build_selection_summary_embed(
    market_type: str,
    selected_items: list[str],
) -> discord.Embed:
    remaining = MAX_ITEM_SELECTION - len(selected_items)
    selected_text = "\n".join(
        f"{index}. {display_item_name(item)}"
        for index, item in enumerate(selected_items, start=1)
    )

    embed = discord.Embed(
        title="🛒 플리마켓 아이템 선택 현황",
        description=(
            f"{selected_text}\n\n"
            f"현재 **{len(selected_items)}개** 선택 · "
            f"추가 가능 **{remaining}개**"
        ),
        color=market_color(market_type),
    )
    embed.set_footer(
        text=(
            "다른 종류를 더 검색하거나, 선택 완료를 눌러 홍보 내용을 작성하세요."
        )
    )
    return embed


class FleaMarketSelectionSummaryView(discord.ui.View):
    def __init__(
        self,
        *,
        market_type: str,
        user_id: int,
        selected_items: list[str],
        search_terms: list[str],
    ):
        super().__init__(timeout=180)
        self.market_type = market_type
        self.user_id = user_id
        self.selected_items = selected_items
        self.search_terms = search_terms

        if len(selected_items) >= MAX_ITEM_SELECTION:
            self.add_more.disabled = True

    async def check_user(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "❌ 신청한 사용자만 사용할 수 있습니다.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(
        label="아이템 더 추가",
        emoji="➕",
        style=discord.ButtonStyle.primary,
    )
    async def add_more(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not await self.check_user(interaction):
            return

        await interaction.response.send_modal(
            FleaMarketItemSearchModal(
                market_type=self.market_type,
                user_id=self.user_id,
                selected_items=self.selected_items,
                search_terms=self.search_terms,
            )
        )

    @discord.ui.button(
        label="선택 완료",
        emoji="✅",
        style=discord.ButtonStyle.success,
    )
    async def finish(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not await self.check_user(interaction):
            return

        await interaction.response.send_modal(
            FleaMarketRegisterModal(
                market_type=self.market_type,
                selected_items=self.selected_items,
                search_terms=self.search_terms,
            )
        )


class FleaMarketItemSelect(discord.ui.Select):
    def __init__(
        self,
        *,
        market_type: str,
        user_id: int,
        search_term: str,
        item_names: list[str],
        selected_items: list[str],
        search_terms: list[str],
    ):
        self.market_type = market_type
        self.user_id = user_id
        self.search_term = search_term
        self.selected_items = selected_items
        self.search_terms = search_terms

        remaining = MAX_ITEM_SELECTION - len(selected_items)
        options = [
            discord.SelectOption(
                label=display_item_name(item_name)[:100],
                value=item_name[:100],
            )
            for item_name in item_names
            if item_name not in selected_items
        ]

        super().__init__(
            placeholder=(
                f"추가할 아이템을 최대 {remaining}개 선택해주세요."
            ),
            min_values=1,
            max_values=min(remaining, len(options)),
            options=options,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ 신청한 사용자만 선택할 수 있습니다.",
                ephemeral=True,
            )
            return

        combined_items = list(
            dict.fromkeys(
                [*self.selected_items, *self.values]
            )
        )[:MAX_ITEM_SELECTION]

        combined_terms = list(
            dict.fromkeys(
                [*self.search_terms, self.search_term]
            )
        )

        await interaction.response.edit_message(
            embed=build_selection_summary_embed(
                self.market_type,
                combined_items,
            ),
            view=FleaMarketSelectionSummaryView(
                market_type=self.market_type,
                user_id=self.user_id,
                selected_items=combined_items,
                search_terms=combined_terms,
            ),
        )


class FleaMarketItemSelectView(discord.ui.View):
    def __init__(
        self,
        *,
        market_type: str,
        user_id: int,
        search_term: str,
        item_names: list[str],
        selected_items: list[str],
        search_terms: list[str],
    ):
        super().__init__(timeout=120)
        self.add_item(
            FleaMarketItemSelect(
                market_type=market_type,
                user_id=user_id,
                search_term=search_term,
                item_names=item_names,
                selected_items=selected_items,
                search_terms=search_terms,
            )
        )


class FleaMarketItemSearchModal(discord.ui.Modal):
    def __init__(
        self,
        market_type: str,
        user_id: int,
        selected_items: list[str] | None = None,
        search_terms: list[str] | None = None,
    ):
        super().__init__(
            title=f"플리마켓 {market_type} 아이템 검색"
        )
        self.market_type = market_type
        self.user_id = user_id
        self.selected_items = list(selected_items or [])
        self.search_terms = list(search_terms or [])

        self.search_term = discord.ui.TextInput(
            label="아이템 검색어",
            placeholder="예) 금별요리, 레몬, 주괴",
            required=True,
            min_length=2,
            max_length=30,
        )
        self.add_item(self.search_term)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ 신청한 사용자만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        remaining = MAX_ITEM_SELECTION - len(self.selected_items)

        if remaining <= 0:
            await interaction.response.send_message(
                "❌ 이미 아이템 5개를 모두 선택했습니다.",
                ephemeral=True,
            )
            return

        search_term = normalize_single_line(
            self.search_term.value
        )
        item_names = [
            item
            for item in search_market_items(search_term)
            if item not in self.selected_items
        ]

        if not item_names:
            await interaction.response.send_message(
                (
                    f"❌ `{search_term}`와 관련된 새 아이템을 "
                    "시세 데이터에서 찾지 못했습니다.\n"
                    "다른 검색어로 다시 시도해주세요."
                ),
                ephemeral=True,
            )
            return

        item_lines = "\n".join(
            f"• {display_item_name(item_name)}"
            for item_name in item_names
        )

        embed = discord.Embed(
            title="🔎 여러 아이템이 검색되었습니다.",
            description=(
                f"검색어: **{search_term}**\n"
                f"기존 선택: **{len(self.selected_items)}개**\n\n"
                f"{item_lines}\n\n"
                f"아래 목록에서 아이템을 "
                f"최대 **{remaining}개** 더 선택해주세요."
            ),
            color=market_color(self.market_type),
        )
        embed.set_footer(
            text=(
                "선택 후 다른 검색어로 아이템을 더 추가할 수 있습니다."
            )
        )

        await interaction.response.send_message(
            embed=embed,
            view=FleaMarketItemSelectView(
                market_type=self.market_type,
                user_id=self.user_id,
                search_term=search_term,
                item_names=item_names,
                selected_items=self.selected_items,
                search_terms=self.search_terms,
            ),
            ephemeral=True,
        )


class FleaMarketRegisterView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id

    async def check_user(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "❌ 신청한 사용자만 선택할 수 있습니다.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(
        label="판매",
        emoji="🟢",
        style=discord.ButtonStyle.success,
    )
    async def select_sell(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not await self.check_user(interaction):
            return

        await interaction.response.send_modal(
            FleaMarketItemSearchModal(
                market_type="판매",
                user_id=self.user_id,
            )
        )

    @discord.ui.button(
        label="구매",
        emoji="🔴",
        style=discord.ButtonStyle.danger,
    )
    async def select_buy(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not await self.check_user(interaction):
            return

        await interaction.response.send_modal(
            FleaMarketItemSearchModal(
                market_type="구매",
                user_id=self.user_id,
            )
        )

