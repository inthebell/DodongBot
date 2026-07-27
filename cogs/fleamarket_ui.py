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
from utils.channel_manager import get_channel_id


OWNER_ID = 478834154595811328


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

    if any(len(keyword) > 10 for keyword in keywords):
        return None, "❌ 각 세부 키워드는 최대 10자까지 입력할 수 있습니다."

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


async def send_new_approval_message(
    interaction: discord.Interaction,
    ad: dict,
) -> bool:
    if interaction.guild is None:
        return False

    approval_channel_id = get_channel_id(
        interaction.guild.id,
        "fleamarket_approval",
    )

    if approval_channel_id is None:
        return False

    approval_channel = interaction.guild.get_channel(
        approval_channel_id
    )

    if not isinstance(approval_channel, discord.TextChannel):
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
    def __init__(self, market_type: str):
        super().__init__(
            title=f"플리마켓 {market_type} 홍보 등록"
        )
        self.market_type = market_type

        self.category = discord.ui.TextInput(
            label="분류 (쉼표로 최대 5개)",
            placeholder="예) 작물, 3티어작물, 농작물",
            required=True,
            max_length=60,
        )
        self.keywords = discord.ui.TextInput(
            label="세부 검색 키워드",
            placeholder="예) 레몬, 감자, 당근",
            required=True,
            max_length=60,
        )
        self.description = discord.ui.TextInput(
            label="홍보 문구",
            placeholder="예) 3티어 작물 판매합니다.",
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
        self.add_item(self.keywords)
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

        if has_existing_ad(
            interaction.guild.id,
            interaction.user.id,
            self.market_type,
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
        stored_keywords = ",".join(keywords)

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

        approval_channel_id = get_channel_id(
            interaction.guild.id,
            "fleamarket_approval",
        )

        if approval_channel_id is None:
            delete_ad(ad_id)
            await interaction.response.send_message(
                "❌ 플리마켓 승인 채널이 설정되지 않았습니다.",
                ephemeral=True,
            )
            return

        approval_channel = interaction.guild.get_channel(
            approval_channel_id
        )

        if not isinstance(approval_channel, discord.TextChannel):
            delete_ad(ad_id)
            await interaction.response.send_message(
                "❌ 설정된 승인 채널을 찾을 수 없습니다.",
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
            name="세부 키워드",
            value=" · ".join(keywords),
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
            FleaMarketRegisterModal("판매")
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
            FleaMarketRegisterModal("구매")
        )
