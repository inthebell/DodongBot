import json
import re
import discord
from discord import app_commands
from discord.ext import commands

ROLE_ID = 1517877280976801862
PASS_SCORE = 7
DATA_PATH = "data/verify_data.json"

sessions = {}


def load_questions():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_answer(text: str) -> str:
    return text.strip().replace(" ", "").lower()


def check_answer(question, user_answer: str, member: discord.Member) -> bool:
    answer = user_answer.strip()

    if question["type"] == "nickname":
        # 형식: 한글/닉네임 [영문인게임닉네임]
        pattern = r"^[가-힣A-Za-z0-9_]{1,20}\s*\[[A-Za-z0-9_]{2,20}\]$"

        if re.match(pattern, answer) is None:
            return False

        # 실제 서버 닉네임과 입력값이 같아야 통과
        server_nickname = member.nick or member.name

        return normalize_answer(answer) == normalize_answer(server_nickname)

    if question["type"] == "ox":
        ox_map = {
            "o": "o",
            "ㅇ": "o",
            "x": "x",
            "ㄴ": "x"
        }

        user = normalize_answer(answer)
        correct = question["answer"].lower()

        return ox_map.get(user) == correct

    if question["type"] == "text":
        user = normalize_answer(answer)
        answers = [normalize_answer(a) for a in question["answers"]]

        return user in answers

    return False


class VerifyAnswerModal(discord.ui.Modal):
    def __init__(self, user_id: int):
        self.user_id = user_id

        session = sessions[user_id]
        self.question_index = session["index"]
        self.question = session["questions"][self.question_index]

        super().__init__(title=f"입주 인증 {self.question_index + 1}/10")

        self.answer = discord.ui.TextInput(
            label="답변을 입력해주세요",
            style=discord.TextStyle.paragraph,
            placeholder=self.question["question"],
            required=True,
            max_length=300
        )

        self.add_item(self.answer)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "본인의 인증만 진행할 수 있습니다.",
                ephemeral=True
            )
            return

        session = sessions[self.user_id]

        is_correct = check_answer(
            self.question,
            str(self.answer.value),
            interaction.user
        )

        # 1번 닉네임 문제는 틀리면 다음 문제로 넘어가지 않음
        if self.question["type"] == "nickname" and not is_correct:
            answer = str(self.answer.value).strip()
            server_nickname = interaction.user.nick or interaction.user.name

            pattern = r"^[가-힣A-Za-z0-9_]{1,20}\s*\[[A-Za-z0-9_]{2,20}\]$"

            if re.match(pattern, answer) is None:
                await interaction.response.send_message(
                    "❌ 닉네임 형식이 올바르지 않습니다.\n\n"
                    "아래 예시처럼 입력해주세요.\n"
                    "예시 : 디얼 [new_dear]",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ 닉네임 확인에 실패했습니다.\n\n"
                    "입력한 닉네임과 현재 도동마을 서버 별명이 일치하지 않습니다.\n\n"
                    "먼저 **도동마을 디스코드 서버 별명을 인게임 닉네임과 동일하게 변경**한 후 다시 인증해주세요.\n\n"
                    f"현재 서버 별명 : {server_nickname}\n"
                    f"입력한 닉네임 : {answer}",
                    ephemeral=True
                )
            return

        if is_correct:
            session["score"] += 1

        session["index"] += 1

        if session["index"] >= len(session["questions"]):
            score = session["score"]

            if score >= PASS_SCORE:
                role = interaction.guild.get_role(ROLE_ID)

                if role:
                    await interaction.user.add_roles(role)
                    result_text = (
                        "🎉 **입주 인증 완료**\n\n"
                        f"정답: **{score} / {len(session['questions'])}**\n\n"
                        "✅ 인증 성공!\n"
                        f"`{role.name}` 역할이 지급되었습니다.\n\n"
                        "공지 채널의 공지사항도 숙지 부탁드립니다.\n"
                        "감사합니다."
                    )
                else:
                    result_text = (
                        "🎉 **입주 인증 완료**\n\n"
                        f"정답: **{score} / 10**\n\n"
                        f"✅ 인증은 성공했지만 역할을 찾지 못했습니다.\n"
                        "역할 이름을 확인해주세요."
                    )
            else:
                result_text = (
                    "❌ **입주 인증 실패**\n\n"
                    f"정답: **{score} / 10**\n\n"
                    "7문제 이상 정답 시 인증됩니다.\n"
                    "마을 공지를 다시 읽고 재도전해주세요."
                )

            sessions.pop(self.user_id, None)

            await interaction.response.send_message(
                result_text,
                ephemeral=True
            )
            return

        next_view = VerifyNextView(self.user_id)

        await interaction.response.send_message(
            "✅ 답변이 제출되었습니다.\n\n"
            "다음 문제로 이동해주세요.\n"
            f"현재 진행: **{session['index']} / {len(session['questions'])}**",
            view=next_view,
            ephemeral=True
        )


class VerifyNextView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

    @discord.ui.button(label="다음 문제", style=discord.ButtonStyle.primary)
    async def next_question(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "본인의 인증만 진행할 수 있습니다.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            VerifyAnswerModal(self.user_id)
        )


class VerifyStartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ 인증하기", style=discord.ButtonStyle.success)
    async def start_verify(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        questions = load_questions()

        sessions[interaction.user.id] = {
            "index": 0,
            "score": 0,
            "questions": questions
        }

        await interaction.response.send_modal(
            VerifyAnswerModal(interaction.user.id)
        )


class Verify(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="인증설정", description="입주 인증 버튼을 생성합니다.")
    @app_commands.checks.has_permissions(administrator=True)
    async def verify_setup(self, interaction: discord.Interaction):

        embed = discord.Embed(
            title="📖 도동마을 입주 인증",
            description=(
                "도동마을 입주 전 반드시 마을 공지를 모두 읽어주세요.\n\n"
                "닉네임 확인 후 총 **9문제**가 출제되며,\n"
                "**7문제 이상 정답** 시 입주 인증이 완료됩니다.\n\n"
                "인증을 시작하려면 아래 버튼을 눌러주세요."
            ),
            color=0xF4C26B
        )

        embed.set_footer(text="DodongBot 입주 인증")

        await interaction.response.send_message(
            "✅ 입주 인증 메시지를 생성했습니다.",
            ephemeral=True
        )

        await interaction.channel.send(
            embed=embed,
            view=VerifyStartView()
        )

async def setup(bot):
    await bot.add_cog(Verify(bot))
