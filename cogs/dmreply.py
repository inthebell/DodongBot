import re
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands


OWNER_ID = 478834154595811328
DM_LOG_CHANNEL_ID = 1525343943867498668

KST = timezone(timedelta(hours=9))


class DMReply(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def create_reply_embed(self, 내용: str):
        now = datetime.now(KST)

        embed = discord.Embed(
            title="📨 도동봇 답변",
            description=내용,
            color=discord.Color.green(),
            timestamp=now
        )

        embed.set_author(
            name="도동봇 고객지원",
            icon_url=self.bot.user.display_avatar.url
        )

        embed.set_footer(
            text="DodongBot Support"
        )

        return embed

    def get_user_id_from_thread(
        self,
        thread: discord.Thread
    ):
        match = re.search(
            r"\((\d{15,22})\)$",
            thread.name
        )

        if match is None:
            return None

        return int(match.group(1))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if message.author.id != OWNER_ID:
            return

        if not isinstance(message.channel, discord.Thread):
            return

        if message.channel.parent_id != DM_LOG_CHANNEL_ID:
            return

        내용 = message.content.strip()

        if not 내용:
            await message.reply(
                "❌ 답장 내용을 입력해 주세요.",
                mention_author=False,
                delete_after=5
            )
            return

        user_id = self.get_user_id_from_thread(
            message.channel
        )

        if user_id is None:
            await message.reply(
                "❌ 스레드 이름에서 사용자 ID를 찾지 못했습니다.",
                mention_author=False,
                delete_after=7
            )
            return

        try:
            target_user = await self.bot.fetch_user(
                user_id
            )

            reply_embed = self.create_reply_embed(
                내용
            )

            await target_user.send(
                embed=reply_embed
            )

            await message.channel.send(
                embed=reply_embed
            )

            try:
                await message.delete()
            except discord.Forbidden:
                pass

        except discord.Forbidden:
            await message.reply(
                "❌ 상대방이 DM을 차단했거나 메시지를 받을 수 없습니다.",
                mention_author=False,
                delete_after=7
            )

        except discord.NotFound:
            await message.reply(
                "❌ 해당 사용자를 찾을 수 없습니다.",
                mention_author=False,
                delete_after=7
            )

        except Exception as e:
            print(f"스레드 DM 답장 오류: {e}")

            await message.reply(
                "❌ 답장을 보내는 중 오류가 발생했습니다.",
                mention_author=False,
                delete_after=7
            )

    @app_commands.command(
        name="답장",
        description="사용자 ID를 입력해 도동봇 DM으로 답장을 보냅니다."
    )
    @app_commands.describe(
        user_id="답장을 받을 사용자 ID",
        내용="사용자에게 보낼 답장 내용"
    )
    async def reply_dm(
        self,
        interaction: discord.Interaction,
        user_id: str,
        내용: str
    ):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message(
                "❌ 이 명령어를 사용할 권한이 없습니다.",
                ephemeral=True
            )
            return

        if interaction.channel_id != DM_LOG_CHANNEL_ID:
            await interaction.response.send_message(
                "❌ 이 명령어는 문의-로그 채널에서만 사용할 수 있습니다.",
                ephemeral=True
            )
            return

        try:
            target_user = await self.bot.fetch_user(
                int(user_id)
            )

            reply_embed = self.create_reply_embed(
                내용
            )

            await target_user.send(
                embed=reply_embed
            )

            await interaction.response.send_message(
                f"✅ **{target_user}**님에게 답장을 보냈습니다.",
                ephemeral=True
            )

        except ValueError:
            await interaction.response.send_message(
                "❌ 사용자 ID는 숫자로 입력해 주세요.",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ 상대방이 DM을 차단했거나 메시지를 받을 수 없습니다.",
                ephemeral=True
            )

        except discord.NotFound:
            await interaction.response.send_message(
                "❌ 해당 사용자를 찾을 수 없습니다.",
                ephemeral=True
            )

        except Exception as e:
            print(f"DM 답장 명령어 오류: {e}")

            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ 답장을 보내는 중 오류가 발생했습니다.",
                    ephemeral=True
                )


async def setup(bot):
    await bot.add_cog(DMReply(bot))