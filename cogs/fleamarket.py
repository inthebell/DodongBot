import asyncio
import random
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.fleamarket_db import (
    cancel_ad_by_owner,
    create_database,
    delete_user_ad,
    expire_ads,
    get_ad,
    get_management_ads,
    get_pending_ads,
    get_user_ad,
    get_user_ads,
    search_active_ads,
)
from cogs.fleamarket_ui import (
    FleaMarketApprovalView,
    FleaMarketRegisterView,
    FleaMarketUserEditModal,
    format_expiration,
    format_remaining_time,
)
from utils.channel_manager import (
    get_channel_id,
    remove_channel_id,
    set_channel_id,
)


FLEAMARKET_GUILD_ID = 1525343469663682601
OWNER_ID = 478834154595811328

KST = timezone(timedelta(hours=9))

TYPE_CHOICES = [
    app_commands.Choice(name="판매", value="판매"),
    app_commands.Choice(name="구매", value="구매"),
]


def status_text(status: str) -> str:
    return {
        "pending": "🟡 승인 대기",
        "active": "🟢 노출 중",
        "expired": "⚪ 만료",
        "rejected": "🔴 반려",
        "cancelled": "⚫ 운영자 취소",
        "deleted": "⚫ 본인 삭제",
    }.get(status, status)


class FleaMarket(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
    ):
        self.bot = bot
        create_database()
        self.restore_pending_views()
        self.expiration_loop.start()

    def cog_unload(self) -> None:
        self.expiration_loop.cancel()

    fleamarket_group = app_commands.Group(
        name="플리마켓",
        description="플리마켓 홍보 및 검색 기능입니다.",
        guild_ids=[FLEAMARKET_GUILD_ID],
    )

    def restore_pending_views(self) -> None:
        for ad in get_pending_ads():
            self.bot.add_view(
                FleaMarketApprovalView(ad["id"]),
                message_id=ad["approval_message_id"],
            )

    def is_owner(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        return interaction.user.id == OWNER_ID

    async def check_guild(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return False

        if interaction.guild.id != FLEAMARKET_GUILD_ID:
            await interaction.response.send_message(
                "❌ 현재 플리마켓 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return False

        return True

    async def check_owner_and_guild(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if not self.is_owner(interaction):
            await interaction.response.send_message(
                "❌ 이 명령어는 도동봇 운영자만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return False

        return await self.check_guild(interaction)

    @tasks.loop(minutes=1)
    async def expiration_loop(self) -> None:
        expire_ads()

    @expiration_loop.before_loop
    async def before_expiration_loop(self) -> None:
        await self.bot.wait_until_ready()

    @fleamarket_group.command(
        name="홍보등록",
        description="무료 플리마켓 홍보 등록 신청서를 작성합니다.",
    )
    async def register_ad(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not await self.check_guild(interaction):
            return

        approval_channel_id = get_channel_id(
            interaction.guild.id,
            "fleamarket_approval",
        )

        if approval_channel_id is None:
            await interaction.response.send_message(
                "❌ 플리마켓 승인 채널이 아직 설정되지 않았습니다.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🏪 플리마켓 무료 홍보 등록",
            description=(
                "등록할 홍보의 거래 구분을 선택해주세요.\n\n"
                "🟢 판매\n"
                "🔴 구매\n\n"
                "※ 운영자 승인 후 3일간 검색 결과에 노출됩니다.\n"
                "※ 홍보 수정 시 검색에서 내려가며 재승인이 필요합니다."
            ),
            color=discord.Color.green(),
        )

        await interaction.response.send_message(
            embed=embed,
            view=FleaMarketRegisterView(
                user_id=interaction.user.id,
            ),
            ephemeral=True,
        )

    @fleamarket_group.command(
        name="내홍보",
        description="내가 신청하거나 등록한 플리마켓 홍보를 확인합니다.",
    )
    async def my_ads(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not await self.check_guild(interaction):
            return

        ads = get_user_ads(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
        )

        if not ads:
            await interaction.response.send_message(
                "❌ 현재 승인 대기 또는 노출 중인 홍보가 없습니다.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🏪 내 플리마켓 홍보",
            description=(
                "홍보 수정은 재승인이 필요하며, "
                "수정 즉시 검색 결과에서 내려갑니다."
            ),
            color=discord.Color.green(),
        )

        for ad in ads:
            expires_text = (
                format_expiration(ad["expires_at"])
                if ad["status"] == "active"
                else "승인 후 3일"
            )

            embed.add_field(
                name=(
                    f"#{ad['id']} · "
                    f"{'🟢' if ad['type'] == '판매' else '🔴'} "
                    f"{ad['type']}"
                ),
                value=(
                    f"상태: {status_text(ad['status'])}\n"
                    f"홍보: {ad['description']}\n"
                    f"이정표: {ad['waypoint']}\n"
                    f"만료: {expires_text}\n"
                    f"남은 기간: "
                    f"{format_remaining_time(ad['expires_at'])}"
                ),
                inline=False,
            )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @fleamarket_group.command(
        name="전체목록",
        description="플리마켓 승인 대기 및 노출 중인 홍보를 확인합니다.",
    )
    async def all_ads(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not await self.check_owner_and_guild(interaction):
            return

        ads = get_management_ads(
            guild_id=interaction.guild.id,
        )

        pending_ads = [
            ad
            for ad in ads
            if ad["status"] == "pending"
        ]

        active_ads = [
            ad
            for ad in ads
            if ad["status"] == "active"
        ]

        today = datetime.now(KST).date()
        today_expiring_ads = []

        for ad in active_ads:
            expires_at = ad.get("expires_at")

            if not expires_at:
                continue

            try:
                expiration = datetime.fromisoformat(expires_at)

                if expiration.tzinfo is None:
                    expiration = expiration.replace(tzinfo=KST)

                if expiration.astimezone(KST).date() == today:
                    today_expiring_ads.append(ad)

            except ValueError:
                continue

        summary_embed = discord.Embed(
            title="🏪 플리마켓 전체 현황",
            description=(
                f"🟢 노출 중: **{len(active_ads)}건**\n"
                f"🟡 승인 대기: **{len(pending_ads)}건**\n"
                f"⏰ 오늘 만료: **{len(today_expiring_ads)}건**"
            ),
            color=discord.Color.green(),
        )
        summary_embed.set_footer(
            text="도동봇 운영자 전용 관리 목록"
        )

        await interaction.response.send_message(
            embed=summary_embed,
            ephemeral=True,
        )

        async def send_ad_pages(
            *,
            title: str,
            page_ads: list[dict],
            color: discord.Color,
        ) -> None:
            if not page_ads:
                return

            page_size = 8

            for start in range(0, len(page_ads), page_size):
                current_ads = page_ads[
                    start:start + page_size
                ]

                page_number = (
                    start // page_size
                ) + 1

                total_pages = (
                    len(page_ads) + page_size - 1
                ) // page_size

                embed = discord.Embed(
                    title=(
                        f"{title} "
                        f"({page_number}/{total_pages})"
                    ),
                    color=color,
                )

                for ad in current_ads:
                    type_emoji = (
                        "🟢"
                        if ad["type"] == "판매"
                        else "🔴"
                    )

                    if ad["status"] == "active":
                        time_text = (
                            f"만료: "
                            f"{format_expiration(ad['expires_at'])}\n"
                            f"남은 기간: "
                            f"{format_remaining_time(ad['expires_at'])}"
                        )
                    else:
                        time_text = "운영자 승인 대기 중"

                    embed.add_field(
                        name=(
                            f"#{ad['id']} · "
                            f"{type_emoji} {ad['type']}"
                        ),
                        value=(
                            f"신청자: <@{ad['user_id']}>\n"
                            f"📢 {ad['description']}\n"
                            f"📍 {ad['waypoint']}\n"
                            f"⏳ {time_text}"
                        ),
                        inline=False,
                    )

                await interaction.followup.send(
                    embed=embed,
                    ephemeral=True,
                )

        await send_ad_pages(
            title="🟡 승인 대기",
            page_ads=pending_ads,
            color=discord.Color.yellow(),
        )

        await send_ad_pages(
            title="🟢 노출 중",
            page_ads=active_ads,
            color=discord.Color.green(),
        )

        await send_ad_pages(
            title="⏰ 오늘 만료 예정",
            page_ads=today_expiring_ads,
            color=discord.Color.orange(),
        )
        
    @fleamarket_group.command(
        name="홍보수정",
        description="내 플리마켓 홍보를 수정하고 재승인을 요청합니다.",
    )
    @app_commands.choices(거래구분=TYPE_CHOICES)
    async def edit_my_ad(
        self,
        interaction: discord.Interaction,
        거래구분: app_commands.Choice[str],
    ) -> None:
        if not await self.check_guild(interaction):
            return

        ad = get_user_ad(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            market_type=거래구분.value,
        )

        if ad is None:
            await interaction.response.send_message(
                f"❌ 수정할 {거래구분.value} 홍보가 없습니다.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            FleaMarketUserEditModal(
                ad_id=ad["id"],
                user_id=interaction.user.id,
            )
        )

    @fleamarket_group.command(
        name="홍보삭제",
        description="내 플리마켓 홍보를 검색 결과 및 승인 대기에서 삭제합니다.",
    )
    @app_commands.choices(거래구분=TYPE_CHOICES)
    async def delete_my_ad(
        self,
        interaction: discord.Interaction,
        거래구분: app_commands.Choice[str],
    ) -> None:
        if not await self.check_guild(interaction):
            return

        ad = get_user_ad(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            market_type=거래구분.value,
        )

        if ad is None:
            await interaction.response.send_message(
                f"❌ 삭제할 {거래구분.value} 홍보가 없습니다.",
                ephemeral=True,
            )
            return

        if not delete_user_ad(
            ad_id=ad["id"],
            user_id=interaction.user.id,
        ):
            await interaction.response.send_message(
                "❌ 홍보를 삭제하지 못했습니다.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            (
                f"✅ 플리마켓 {거래구분.value} 홍보를 삭제했습니다.\n"
                "검색 결과 및 승인 대기에서 즉시 제외됩니다."
            ),
            ephemeral=True,
        )

    @fleamarket_group.command(
        name="홍보취소",
        description="신청 번호로 플리마켓 홍보를 강제로 취소합니다.",
    )
    async def cancel_ad(
        self,
        interaction: discord.Interaction,
        신청번호: int,
    ) -> None:
        if not await self.check_owner_and_guild(interaction):
            return

        ad = get_ad(신청번호)

        if (
            ad is None
            or ad["guild_id"] != interaction.guild.id
            or ad["status"] not in ("pending", "active")
        ):
            await interaction.response.send_message(
                "❌ 취소할 수 있는 홍보를 찾지 못했습니다.",
                ephemeral=True,
            )
            return

        if not cancel_ad_by_owner(
            ad_id=신청번호,
            reviewer_id=interaction.user.id,
        ):
            await interaction.response.send_message(
                "❌ 홍보를 취소하지 못했습니다.",
                ephemeral=True,
            )
            return

        user = self.bot.get_user(ad["user_id"])
        if user is None:
            try:
                user = await self.bot.fetch_user(ad["user_id"])
            except discord.HTTPException:
                user = None

        if user is not None:
            try:
                await user.send(
                    (
                        f"⚠️ 플리마켓 {ad['type']} 홍보 "
                        f"(신청 번호 #{ad['id']})가 운영자에 의해 취소되었습니다."
                    )
                )
            except discord.HTTPException:
                pass

        await interaction.response.send_message(
            (
                f"✅ 신청 번호 #{ad['id']}의 "
                f"{ad['type']} 홍보를 취소했습니다."
            ),
            ephemeral=True,
        )

    @fleamarket_group.command(
        name="채널설정",
        description="현재 채널을 플리마켓 검색 채널로 설정합니다.",
    )
    async def set_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not await self.check_owner_and_guild(interaction):
            return

        if not isinstance(
            interaction.channel,
            discord.TextChannel,
        ):
            await interaction.response.send_message(
                "❌ 일반 텍스트 채널에서만 설정할 수 있습니다.",
                ephemeral=True,
            )
            return

        set_channel_id(
            interaction.guild.id,
            "fleamarket",
            interaction.channel.id,
        )

        await interaction.response.send_message(
            (
                f"✅ {interaction.channel.mention} 채널을 "
                "플리마켓 검색 채널로 설정했습니다."
            ),
            ephemeral=True,
        )

        guide_embed = discord.Embed(
            title="🏪 도동봇 플리마켓",
            description=(
                "판매하거나 구매할 물품을 검색할 수 있는 채널입니다.\n"
                "분류 또는 세부 키워드를 2글자 이상 입력해주세요.\n\n"
                "홍보 등록은 현재 무료이며 운영자 승인 후 3일간 노출됩니다."
            ),
            color=discord.Color.green(),
        )
        guide_embed.set_footer(
            text="판매·구매 각각 최대 3개의 홍보가 표시됩니다."
        )

        await interaction.channel.send(embed=guide_embed)

    @fleamarket_group.command(
        name="채널확인",
        description="현재 설정된 플리마켓 검색 채널을 확인합니다.",
    )
    async def check_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not await self.check_owner_and_guild(interaction):
            return

        channel_id = get_channel_id(
            interaction.guild.id,
            "fleamarket",
        )

        if channel_id is None:
            await interaction.response.send_message(
                "❌ 현재 설정된 플리마켓 검색 채널이 없습니다.",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(channel_id)

        await interaction.response.send_message(
            (
                f"✅ 현재 플리마켓 검색 채널은 {channel.mention}입니다."
                if channel
                else "⚠️ 설정된 채널을 찾을 수 없습니다."
            ),
            ephemeral=True,
        )

    @fleamarket_group.command(
        name="채널해제",
        description="현재 설정된 플리마켓 검색 채널을 해제합니다.",
    )
    async def remove_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not await self.check_owner_and_guild(interaction):
            return

        removed = remove_channel_id(
            interaction.guild.id,
            "fleamarket",
        )

        await interaction.response.send_message(
            (
                "✅ 플리마켓 검색 채널 설정을 해제했습니다."
                if removed
                else "❌ 현재 설정된 플리마켓 검색 채널이 없습니다."
            ),
            ephemeral=True,
        )

    @fleamarket_group.command(
        name="승인채널설정",
        description="현재 채널을 플리마켓 신청 승인 채널로 설정합니다.",
    )
    async def set_approval_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not await self.check_owner_and_guild(interaction):
            return

        if not isinstance(
            interaction.channel,
            discord.TextChannel,
        ):
            await interaction.response.send_message(
                "❌ 일반 텍스트 채널에서만 설정할 수 있습니다.",
                ephemeral=True,
            )
            return

        set_channel_id(
            interaction.guild.id,
            "fleamarket_approval",
            interaction.channel.id,
        )

        await interaction.response.send_message(
            (
                f"✅ {interaction.channel.mention} 채널을 "
                "플리마켓 승인 채널로 설정했습니다."
            ),
            ephemeral=True,
        )

    @fleamarket_group.command(
        name="승인채널확인",
        description="현재 설정된 플리마켓 승인 채널을 확인합니다.",
    )
    async def check_approval_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not await self.check_owner_and_guild(interaction):
            return

        channel_id = get_channel_id(
            interaction.guild.id,
            "fleamarket_approval",
        )

        if channel_id is None:
            await interaction.response.send_message(
                "❌ 현재 설정된 플리마켓 승인 채널이 없습니다.",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(channel_id)

        await interaction.response.send_message(
            (
                f"✅ 현재 플리마켓 승인 채널은 {channel.mention}입니다."
                if channel
                else "⚠️ 설정된 승인 채널을 찾을 수 없습니다."
            ),
            ephemeral=True,
        )

    @fleamarket_group.command(
        name="승인채널해제",
        description="현재 설정된 플리마켓 승인 채널을 해제합니다.",
    )
    async def remove_approval_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not await self.check_owner_and_guild(interaction):
            return

        removed = remove_channel_id(
            interaction.guild.id,
            "fleamarket_approval",
        )

        await interaction.response.send_message(
            (
                "✅ 플리마켓 승인 채널 설정을 해제했습니다."
                if removed
                else "❌ 현재 설정된 플리마켓 승인 채널이 없습니다."
            ),
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message,
    ) -> None:
        if message.author.bot:
            return

        if message.guild is None:
            return

        if message.guild.id != FLEAMARKET_GUILD_ID:
            return

        configured_channel_id = get_channel_id(
            message.guild.id,
            "fleamarket",
        )

        if (
            configured_channel_id is None
            or message.channel.id != configured_channel_id
        ):
            return

        search_term = " ".join(message.content.split())
        normalized_term = "".join(
            search_term.lower().split()
        )

        if not normalized_term:
            return

        if len(normalized_term) < 2:
            try:
                await message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass

            await message.channel.send(
                "❌ 검색어는 2글자 이상 입력해주세요.",
                delete_after=5,
            )
            return

        try:
            await message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

        loading_message = await message.channel.send(
            "🔍 플리마켓 홍보를 검색하고 있습니다..."
        )

        results = search_active_ads(
            guild_id=message.guild.id,
            search_term=search_term,
        )

        sell_ads = results["판매"]
        buy_ads = results["구매"]

        await asyncio.sleep(1.0)

        if not sell_ads and not buy_ads:
            await loading_message.edit(
                content="❌ 해당 검색어로 등록된 플리마켓 홍보가 없습니다."
            )
            await asyncio.sleep(5)

            try:
                await loading_message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass
            return

        selected_sell_ads = random.sample(
            sell_ads,
            min(3, len(sell_ads)),
        )
        selected_buy_ads = random.sample(
            buy_ads,
            min(3, len(buy_ads)),
        )

        sections: list[str] = []

        if selected_sell_ads:
            sell_lines = ["🟢 **판매**"]
            for ad in selected_sell_ads:
                sell_lines.append(
                    f"📢 {ad['description']}\n📍 {ad['waypoint']}"
                )
            sections.append("\n\n".join(sell_lines))

        if selected_buy_ads:
            buy_lines = ["🔴 **구매**"]
            for ad in selected_buy_ads:
                buy_lines.append(
                    f"📢 {ad['description']}\n📍 {ad['waypoint']}"
                )
            sections.append("\n\n".join(buy_lines))

        embed = discord.Embed(
            title=f"🔎 플리마켓 검색 결과 · {search_term}",
            description="\n\n".join(sections),
            color=discord.Color.green(),
        )
        embed.set_footer(
            text="판매·구매 각각 최대 3개의 홍보가 무작위로 표시됩니다."
        )

        await loading_message.edit(
            content=None,
            embed=embed,
        )


async def setup(
    bot: commands.Bot,
) -> None:
    await bot.add_cog(FleaMarket(bot))
