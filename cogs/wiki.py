import discord
from discord import app_commands
from discord.ext import commands

from utils.log_manager import send_use_log

from utils.channel_manager import (
    get_channel_id,
    remove_channel_id,
    set_channel_id,
)
from utils.wiki_manager import wiki_manager


class Wiki(commands.Cog):
    wiki_group = app_commands.Group(
        name="위키",
        description="동글랜드 위키 질문 기능입니다.",
    )

    channel_group = app_commands.Group(
        name="질문채널",
        description="동글랜드 위키 질문채널을 관리합니다.",
        parent=wiki_group,
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @channel_group.command(
        name="설정",
        description="현재 채널을 동글랜드 위키 질문채널로 설정합니다.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ 서버 안에서만 사용할 수 있는 명령어입니다.",
                ephemeral=True,
            )
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ 일반 텍스트 채널에서 실행해주세요.",
                ephemeral=True,
            )
            return

        bot_member = interaction.guild.me

        if bot_member is None:
            await interaction.response.send_message(
                "❌ 도동봇의 서버 권한을 확인할 수 없습니다.",
                ephemeral=True,
            )
            return

        permissions = interaction.channel.permissions_for(bot_member)
        missing_permissions = []

        if not permissions.view_channel:
            missing_permissions.append("채널 보기")

        if not permissions.send_messages:
            missing_permissions.append("메시지 보내기")

        if not permissions.read_message_history:
            missing_permissions.append("메시지 기록 보기")

        if missing_permissions:
            permission_text = "\n".join(
                f"• {permission}"
                for permission in missing_permissions
            )

            await interaction.response.send_message(
                "❌ 도동봇에게 필요한 채널 권한이 부족합니다.\n\n"
                f"{permission_text}\n\n"
                "권한을 허용한 뒤 다시 설정해주세요.",
                ephemeral=True,
            )
            return

        set_channel_id(
            interaction.guild.id,
            "wiki",
            interaction.channel.id,
        )

        await interaction.response.send_message(
            "✅ 동글랜드 위키 질문채널을 설정했습니다.\n\n"
            f"설정된 채널: {interaction.channel.mention}\n\n"
            "이제 이 채널에 `대장장이마동석`, `동협`, "
            "`낚시 레벨업`처럼 궁금한 내용을 입력하면 "
            "관련 위키 내용을 찾아드립니다.\n\n"
            "※ 도동봇은 질문과 관련된 큰 틀의 내용을 안내합니다.\n"
            "※ 아직 정확한 상세 내용이나 세부 안내가 어려울 수 있으니, "
            "답변 아래의 동글랜드 위키 바로가기도 함께 참고해주세요.",
            ephemeral=True,
        )

    @channel_group.command(
        name="확인",
        description="현재 설정된 동글랜드 위키 질문채널을 확인합니다.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def check_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ 서버 안에서만 사용할 수 있는 명령어입니다.",
                ephemeral=True,
            )
            return

        channel_id = get_channel_id(
            interaction.guild.id,
            "wiki",
        )

        if channel_id is None:
            await interaction.response.send_message(
                "❌ 현재 설정된 동글랜드 위키 질문채널이 없습니다.\n\n"
                "원하는 채널에서 `/위키 질문채널 설정`을 "
                "사용해주세요.",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(channel_id)

        if channel is None:
            await interaction.response.send_message(
                "⚠️ 설정된 채널을 찾을 수 없습니다.\n\n"
                "채널이 삭제되었을 수 있으므로 "
                "다시 설정해주세요.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "📚 현재 동글랜드 위키 질문채널\n\n"
            f"{channel.mention}",
            ephemeral=True,
        )

    @channel_group.command(
        name="해제",
        description="동글랜드 위키 질문채널 설정을 해제합니다.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ 서버 안에서만 사용할 수 있는 명령어입니다.",
                ephemeral=True,
            )
            return

        removed = remove_channel_id(
            interaction.guild.id,
            "wiki",
        )

        if not removed:
            await interaction.response.send_message(
                "❌ 현재 설정된 동글랜드 위키 질문채널이 없습니다.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "✅ 동글랜드 위키 질문채널 설정을 해제했습니다.",
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

        if not isinstance(message.channel, discord.TextChannel):
            return

        configured_channel_id = get_channel_id(
            message.guild.id,
            "wiki",
        )

        if configured_channel_id is None:
            return

        if message.channel.id != configured_channel_id:
            return

        query = message.content.strip()

        if not query:
            return

        async with message.channel.typing():
            try:
                result = await wiki_manager.search(query)
            except Exception:
                await message.reply(
                    "❌ 동글랜드 위키를 불러오는 중 문제가 발생했습니다.\n"
                    "잠시 후 다시 질문해주세요.",
                    mention_author=False,
                )
                return

        if result is None:
            embed = discord.Embed(
                title="🔎 관련 위키 내용을 찾지 못했습니다",
                description=(
                    f"질문: **{query}**\n\n"
                    "검색어를 조금 더 짧게 입력해보세요.\n"
                    "예: `대장장이마동석` → `마동석`"
                ),
                color=discord.Color.orange(),
            )
            embed.add_field(
                name="출처",
                value="동글랜드 위키",
                inline=False,
            )
            embed.add_field(
                name="관련 주소",
                value="https://dongle-land.gitbook.io/dongle_land",
                inline=False,
            )

            await message.reply(
                embed=embed,
                mention_author=False,
            )

            await send_use_log(
                bot=self.bot,
                title="📚 위키 검색",
                user=message.author,
                guild=message.guild,
                channel=message.channel,
                search_query=query
            )

            return

        embed = discord.Embed(
            title=f"📚 {result.title}",
            description=result.summary,
            color=discord.Color.green(),
        )
        embed.add_field(
            name="질문",
            value=query[:1024],
            inline=False,
        )
        embed.add_field(
            name="출처",
            value="동글랜드 위키",
            inline=False,
        )
        embed.add_field(
            name="관련 주소",
            value=f"[해당 위키 페이지 바로가기]({result.url})",
            inline=False,
        )
        embed.set_footer(
            text="위키 내용이 변경되면 답변도 달라질 수 있습니다."
        )

        await message.reply(
            embed=embed,
            mention_author=False,
        )

        await send_use_log(
            bot=self.bot,
            title="📚 위키 검색",
            user=message.author,
            guild=message.guild,
            channel=message.channel,
            search_query=query
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(Wiki(bot))