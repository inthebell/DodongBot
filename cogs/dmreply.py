import discord
from discord import app_commands
from discord.ext import commands


OWNER_ID = 478834154595811328
DM_LOG_CHANNEL_ID = 1525343943867498668


class DMReply(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="답장",
        description="도동봇으로 문의한 사용자에게 DM 답장을 보냅니다."
    )
    @app_commands.describe(
        user_id="문의 로그에 표시된 사용자 ID",
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
            target_user = await self.bot.fetch_user(int(user_id))

            embed = discord.Embed(
                title="📨 도동봇 문의 답변",
                description=내용,
                color=discord.Color.green()
            )

            await target_user.send(embed=embed)

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
            print(f"DM 답장 전송 오류: {e}")

            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ 답장을 보내는 중 오류가 발생했습니다.",
                    ephemeral=True
                )


async def setup(bot):
    await bot.add_cog(DMReply(bot))