import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands


# 도동봇 관리자 디스코드 ID
OWNER_ID = 478834154595811328

# 게임 규칙 명령어를 사용할 서버 ID
GAME_GUILD_ID = 1529024919210299444

# 게임 규칙 메시지 정보 저장 파일
DATA_FILE = Path("data/game_rules.json")


def load_game_rules() -> dict:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not DATA_FILE.exists():
        return {}

    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}


def save_game_rules(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


GAME_CHOICES = [
    app_commands.Choice(name="🎴 블랙잭", value="블랙잭"),
    app_commands.Choice(name="💎 바카라", value="바카라"),
    app_commands.Choice(name="🎰 잭팟", value="잭팟"),
    app_commands.Choice(name="📈 업다운", value="업다운"),
    app_commands.Choice(name="🎟️ 양털 로또", value="양털 로또"),
    app_commands.Choice(name="🎲 랜덤 다이스", value="랜덤 다이스"),
]


class GameRuleModal(discord.ui.Modal):
    def __init__(
        self,
        cog: "GameRules",
        game_name: str,
        channel: discord.TextChannel,
        mode: str,
        current_title: str = "",
        current_content: str = "",
    ):
        modal_title = "게임 규칙 등록" if mode == "register" else "게임 규칙 수정"
        super().__init__(title=modal_title)

        self.cog = cog
        self.game_name = game_name
        self.channel = channel
        self.mode = mode

        self.rule_title = discord.ui.TextInput(
            label="규칙 제목",
            placeholder="예: 🃏 블랙잭 게임 규칙",
            default=current_title,
            max_length=256,
        )

        self.rule_content = discord.ui.TextInput(
            label="게임 규칙 내용",
            placeholder="게임 방법, 배팅금, 배당금, 주의사항 등을 입력해 주세요.",
            style=discord.TextStyle.paragraph,
            default=current_content,
            max_length=4000,
        )

        self.add_item(self.rule_title)
        self.add_item(self.rule_content)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        title = self.rule_title.value.strip()
        content = self.rule_content.value.strip()

        embed = discord.Embed(
            title=title,
            description=content,
            color=discord.Color.dark_blue(),
        )

        embed.set_footer(text="도동하우스 게임 규칙")

        rules_data = load_game_rules()

        if self.mode == "register":
            old_data = rules_data.get(self.game_name)

            if old_data:
                await interaction.followup.send(
                    f"이미 **{self.game_name}** 규칙이 등록되어 있습니다.\n"
                    f"`/게임규칙 수정`을 사용해 주세요.",
                    ephemeral=True,
                )
                return

            try:
                message = await self.channel.send(embed=embed)
            except discord.Forbidden:
                await interaction.followup.send(
                    f"{self.channel.mention} 채널에 메시지를 보낼 권한이 없습니다.",
                    ephemeral=True,
                )
                return
            except discord.HTTPException:
                await interaction.followup.send(
                    "게임 규칙 메시지를 전송하는 중 오류가 발생했습니다.",
                    ephemeral=True,
                )
                return

            rules_data[self.game_name] = {
                "channel_id": self.channel.id,
                "message_id": message.id,
                "title": title,
                "content": content,
            }

            save_game_rules(rules_data)

            await interaction.followup.send(
                f"✅ **{self.game_name}** 규칙을 {self.channel.mention} 채널에 등록했습니다.",
                ephemeral=True,
            )
            return

        game_data = rules_data.get(self.game_name)

        if not game_data:
            await interaction.followup.send(
                f"등록된 **{self.game_name}** 규칙을 찾을 수 없습니다.",
                ephemeral=True,
            )
            return

        channel_id = game_data.get("channel_id")
        message_id = game_data.get("message_id")

        saved_channel = self.cog.bot.get_channel(channel_id)

        if not isinstance(saved_channel, discord.TextChannel):
            try:
                saved_channel = await self.cog.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                saved_channel = None

        if not isinstance(saved_channel, discord.TextChannel):
            await interaction.followup.send(
                "기존 게임 규칙 채널을 찾을 수 없습니다.",
                ephemeral=True,
            )
            return

        try:
            message = await saved_channel.fetch_message(message_id)
            await message.edit(embed=embed)
        except discord.NotFound:
            await interaction.followup.send(
                "기존 게임 규칙 메시지가 삭제되어 수정할 수 없습니다.\n"
                "`/게임규칙 삭제` 후 다시 등록해 주세요.",
                ephemeral=True,
            )
            return
        except discord.Forbidden:
            await interaction.followup.send(
                "기존 게임 규칙 메시지를 수정할 권한이 없습니다.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "게임 규칙 메시지를 수정하는 중 오류가 발생했습니다.",
                ephemeral=True,
            )
            return

        rules_data[self.game_name]["title"] = title
        rules_data[self.game_name]["content"] = content
        save_game_rules(rules_data)

        await interaction.followup.send(
            f"✅ **{self.game_name}** 규칙을 수정했습니다.",
            ephemeral=True,
        )


class GameRules(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    game_rules_group = app_commands.Group(
        name="게임규칙",
        description="도동하우스 게임 규칙을 관리합니다.",
        guild_ids=[GAME_GUILD_ID],
    )

    async def owner_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message(
                "❌ 도동봇 관리자만 사용할 수 있는 명령어입니다.",
                ephemeral=True,
            )
            return False

        return True

    @game_rules_group.command(
        name="등록",
        description="게임 규칙을 선택한 채널에 등록합니다.",
    )
    @app_commands.choices(게임=GAME_CHOICES)
    @app_commands.describe(
        게임="등록할 게임을 선택해 주세요.",
        채널="게임 규칙을 작성할 채널을 선택해 주세요.",
    )
    async def register_rule(
        self,
        interaction: discord.Interaction,
        게임: app_commands.Choice[str],
        채널: discord.TextChannel,
    ):
        if not await self.owner_check(interaction):
            return

        if interaction.guild_id != GAME_GUILD_ID:
            await interaction.response.send_message(
                "이 서버에서는 사용할 수 없는 명령어입니다.",
                ephemeral=True,
            )
            return

        rules_data = load_game_rules()

        if 게임.value in rules_data:
            await interaction.response.send_message(
                f"이미 **{게임.value}** 규칙이 등록되어 있습니다.\n"
                f"`/게임규칙 수정`을 사용해 주세요.",
                ephemeral=True,
            )
            return

        modal = GameRuleModal(
            cog=self,
            game_name=게임.value,
            channel=채널,
            mode="register",
        )

        await interaction.response.send_modal(modal)

    @game_rules_group.command(
        name="수정",
        description="도동봇이 작성한 기존 게임 규칙을 수정합니다.",
    )
    @app_commands.choices(게임=GAME_CHOICES)
    @app_commands.describe(
        게임="수정할 게임을 선택해 주세요.",
    )
    async def edit_rule(
        self,
        interaction: discord.Interaction,
        게임: app_commands.Choice[str],
    ):
        if not await self.owner_check(interaction):
            return

        rules_data = load_game_rules()
        game_data = rules_data.get(게임.value)

        if not game_data:
            await interaction.response.send_message(
                f"등록된 **{게임.value}** 규칙이 없습니다.",
                ephemeral=True,
            )
            return

        channel_id = game_data.get("channel_id")
        channel = self.bot.get_channel(channel_id)

        if not isinstance(channel, discord.TextChannel):
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                channel = None

        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "기존 게임 규칙 채널을 찾을 수 없습니다.",
                ephemeral=True,
            )
            return

        modal = GameRuleModal(
            cog=self,
            game_name=게임.value,
            channel=channel,
            mode="edit",
            current_title=game_data.get("title", ""),
            current_content=game_data.get("content", ""),
        )

        await interaction.response.send_modal(modal)

    @game_rules_group.command(
        name="삭제",
        description="도동봇이 작성한 게임 규칙을 삭제합니다.",
    )
    @app_commands.choices(게임=GAME_CHOICES)
    @app_commands.describe(
        게임="삭제할 게임을 선택해 주세요.",
    )
    async def delete_rule(
        self,
        interaction: discord.Interaction,
        게임: app_commands.Choice[str],
    ):
        if not await self.owner_check(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        rules_data = load_game_rules()
        game_data = rules_data.get(게임.value)

        if not game_data:
            await interaction.followup.send(
                f"등록된 **{게임.value}** 규칙이 없습니다.",
                ephemeral=True,
            )
            return

        channel_id = game_data.get("channel_id")
        message_id = game_data.get("message_id")

        channel = self.bot.get_channel(channel_id)

        if not isinstance(channel, discord.TextChannel):
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                channel = None

        if isinstance(channel, discord.TextChannel):
            try:
                message = await channel.fetch_message(message_id)
                await message.delete()
            except discord.NotFound:
                pass
            except discord.Forbidden:
                await interaction.followup.send(
                    "게임 규칙 메시지를 삭제할 권한이 없습니다.",
                    ephemeral=True,
                )
                return
            except discord.HTTPException:
                await interaction.followup.send(
                    "게임 규칙 메시지를 삭제하는 중 오류가 발생했습니다.",
                    ephemeral=True,
                )
                return

        rules_data.pop(게임.value, None)
        save_game_rules(rules_data)

        await interaction.followup.send(
            f"✅ **{게임.value}** 규칙을 삭제했습니다.",
            ephemeral=True,
        )

    @game_rules_group.command(
        name="확인",
        description="현재 등록된 게임 규칙을 확인합니다.",
    )
    async def check_rules(self, interaction: discord.Interaction):
        if not await self.owner_check(interaction):
            return

        rules_data = load_game_rules()

        if not rules_data:
            await interaction.response.send_message(
                "현재 등록된 게임 규칙이 없습니다.",
                ephemeral=True,
            )
            return

        lines = []

        for game_name, game_data in rules_data.items():
            channel_id = game_data.get("channel_id")
            message_id = game_data.get("message_id")

            message_url = (
                f"https://discord.com/channels/"
                f"{GAME_GUILD_ID}/{channel_id}/{message_id}"
            )

            lines.append(
                f"**{game_name}**\n"
                f"채널: <#{channel_id}>\n"
                f"[규칙 메시지 바로가기]({message_url})"
            )

        embed = discord.Embed(
            title="🎮 등록된 게임 규칙",
            description="\n\n".join(lines),
            color=discord.Color.dark_blue(),
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(GameRules(bot))