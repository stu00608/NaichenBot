"""
This file contains a cog for AI psychotherapy assistant commands.
"""

import os
import json
import time
import asyncio
import datetime
import traceback
import openai
import discord
import random
from discord.ui import View, Button
from discord.ext import commands
from asgiref.sync import sync_to_async
from assets.utils.chat import Conversation, generate_conversation, num_tokens_from_messages
import assets.settings.setting as setting

logger = setting.logging.getLogger("psy")

openai.api_key = os.getenv("OPENAI_API_KEY")

smart_qa_system_message = """You are a psychotherapist having a pre-counseling assessment with individual. Your goal is to collect enough information list below:
- Personal Information: The patient's personality, 
- Presenting Problem: The patient's current mental health concerns, symptoms, life stressors, and relationship problems.
- History of the Presenting Problem: The onset, pattern, triggers, and previous attempts to cope with or resolve the problem.
- Psychiatric History: Past mental health diagnoses, treatments, hospitalizations, medications, their effectiveness, and the patient's response.
- Medical History: Physical health conditions, surgeries, medications impacting mental health, and any psychological symptoms caused by physical conditions or medication side effects.
- Social History: Patient's childhood, education, work history, relationships, and current living situation to understand sources of stress, trauma, and support.
- Family History: Any significant mental health conditions or problems in the patient's family, including genetic factors and family dynamics.
- Risk Assessment: Identification of any risk factors to the patient or others, such as suicidal ideation, self-harm, or violence.
- Strengths and Coping Mechanisms: Patient's personal strengths, supportive relationships, and healthy coping mechanisms to incorporate into the treatment plan.
- Goals for Therapy: Patient's specific or general aspirations for therapy, whether focused on reducing symptoms, improving mood, or enhancing overall functioning.

You keep chatting with individual like a conversation with friend until you collect enough information, be very friendly and kindly.
"""

smart_qa_first_assistant_message = """{{
    "question_num": 1,
    "is_enough": false,
    "off_topic": false,
    "response": "{}"
}}"""

greeting_candidate_list = [
    "哈囉，初次見面，不知道該怎麼稱呼您呢？",
    "嗨，初次見面，請問該怎麼稱呼您呢？",
    "嗨，很高興見到您，可以告訴我您的名字嗎？",
    "嗨，很高興遇見您，請問該怎麼稱呼您呢？",
    "嗨，很高興認識您，請問該怎麼稱呼您呢？",
    "哈囉，初次見面，您願意告訴我您的名字嗎？",
    "嗨，初次見面，我該怎麼稱呼你呢？",
]

smart_qa_user_template = """Individual: {}

You keep chatting with individual until you collect enough information, be very friendly and kindly, do not be formal.
You are only allowed to ask up to 14 questions, once you collected enough information, end the conversation immediately.
If individual replied off-topic, remind individual in your response
You must respond in Traditional Chinese with valid JSON of form:
```
{{
    "question_num": <int number of question>,
    "is_enough": <true or false>,
    "off_topic": <true or false>,
    "response": "<Your next question to ask>"
}}
```"""

smart_qa_first_prompt = [{"role": "system", "content": smart_qa_system_message}, {
    "role": "assistant", "content": smart_qa_first_assistant_message}]

smart_qa_report_template = """{
    "background_description": "<background you analyzed in Traditional Chinese>",
    "chat_style": "<chat style you analyzed in Traditional Chinese>",
    "report": {
        "name": "<Traditional Chinese string>",
        "personal_information": "<Traditional Chinese string>",
        "presenting_issue": "<Traditional Chinese string>",
        "issue_history": "<Traditional Chinese string>",
        "psychiatric_history": "<Traditional Chinese string>",
        "medical_history": "<Traditional Chinese string>",
        "social_history": "<Traditional Chinese string>",
        "family_history": "<Traditional Chinese string>",
        "risk_assesment": "<Traditional Chinese string>",
        "strengths_and_coping_mechanism": "<Traditional Chinese string>",
        "therapy_goals": "<Traditional Chinese string>",
        "missing_information": "<Traditional Chinese string>"
    }
}"""


def check_conversation_format(response: dict):
    template = {
        "question_num": 1,
        "is_enough": False,
        "off_topic": False,
        "response": "<Your next question to ask>"
    }
    # Check if response has the exact same structure as template, and the type of each value is correct.
    if not isinstance(response, dict):
        return False
    for key, value in template.items():
        if key not in response:
            return False
        if not isinstance(response[key], type(value)):
            return False
    return True


def check_report_format(response: dict):
    """Check if the response has the same structure and value type as expected."""
    template = json.loads(smart_qa_report_template)

    # Check if the response dictionary has the same keys as the template
    if set(response.keys()) != set(template.keys()):
        return False

    for key, value in template.items():
        # Check if the response value type matches the template value type
        if not isinstance(response[key], type(value)):
            return False

    return True


def make_report_prompt(questions: list, answers: list, return_str: bool = False):
    questions = "\n".join([f"{i+1}. {q}" for i, q in enumerate(questions)])
    text = f"""questions:
{questions}

answers:
{answers}

Based on the questions and answers, summarize a detail report for psychotherapist to better and quicker understand the situation about this individual. 
Based on the questions and answers above as a conversation sequence, analyze the background and chat style in great detail using Traditional Chinese.

You always think step-by-step. Be very thorough and explicit.
You make report only from the facts you know.
You always make the report professionally and objectively.

You must respond in Traditional Chinese with valid JSON of form:
```
{smart_qa_report_template}
```
    """

    if return_str:
        return text

    prompt = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": text}
    ]

    return prompt


def format_report_response(response: dict) -> str:
    """Format the response dictionary values to a Markdown string."""
    markdown = "# {} 的分析報告\n\n## 個人資料\n{}\n\n## 想要解決的問題\n{}\n\n## 問題的緣由\n{}\n\n## 精神病史\n{}\n\n## 疾病歷史\n{}\n\n## 社交歷史\n{}\n\n## 家庭歷史\n{}\n\n## 風險評估\n{}\n\n## 優勢與應對機制\n{}\n\n## 治療目標\n{}\n\n## 遺漏資訊\n{}\n\n---\n\n## 聊天風格\n{}\n\n## 背景描述\n{}\n".format(
        response["report"]["name"],
        response["report"]["personal_information"],
        response["report"]["presenting_issue"],
        response["report"]["issue_history"],
        response["report"]["psychiatric_history"],
        response["report"]["medical_history"],
        response["report"]["social_history"],
        response["report"]["family_history"],
        response["report"]["risk_assesment"],
        response["report"]["strengths_and_coping_mechanism"],
        response["report"]["therapy_goals"],
        response["report"]["missing_information"],
        response["chat_style"],
        response["background_description"]
    )
    return markdown


class PsyGPT(commands.Cog):
    """Cog for PsyGPT commands.
    """

    def __init__(self, bot):
        self.bot = bot

        self.database_path = f"assets/database/psygpt_database/"
        if not os.path.exists(self.database_path):
            os.makedirs(self.database_path)

        self.questionnaire_threads = {}
        self.chatting_threads = {}

        self.database = {}

    def load_database(self, id: str):
        filepath = os.path.join(self.database_path, f"{id}.json")
        try:
            if not os.path.exists(filepath):
                logger.info(
                    f"Database file {filepath} does not exist. Creating one...")
                with open(filepath, "w") as f:
                    json.dump({}, f)
        except Exception as e:
            logger.error(
                f"Failed to load database: {e}, {traceback.format_exc()}")
            return None
        return json.load(open(filepath, "r"))

    def write_database(self, id: str, database: dict):
        filepath = os.path.join(self.database_path, f"{id}.json")
        try:
            json.dump(database, open(filepath, "w"), indent=4)
        except Exception as e:
            logger.error(
                f"Failed to write database: {e}, {traceback.format_exc()}")
            return False
        return True

    @commands.Cog.listener()
    async def on_message(self, ctx):
        user_id = ctx.author.id
        user_discriminator = ctx.author.name + "#" + ctx.author.discriminator
        if ctx.author == self.bot.user:
            # message author is not the bot itself
            return
        if not ctx.guild:
            # message is from a dm
            return
        if ctx.author.id in self.questionnaire_threads \
                and ctx.channel.id == self.questionnaire_threads[ctx.author.id]["thread_id"]:
            # Questionnaire thread
            # TODO: Add support for user message editing

            # Delete any message inside this thread that is not belong to the bot or the user.
            async for msg in ctx.channel.history(limit=None, oldest_first=True):
                if msg.author.id != ctx.author.id and msg.author.id != self.bot.user.id:
                    await msg.delete()

            # If user_discriminator is not in database, add it to the database.
            if str(user_id)+".json" not in os.listdir(self.database_path):
                smart_qa_first_prompt = [{"role": "system", "content": smart_qa_system_message}, {
                    "role": "assistant", "content": smart_qa_first_assistant_message.format(self.questionnaire_threads[ctx.author.id]["greeting"])}]
                self.database[user_discriminator] = {
                    "discriminator": user_discriminator,
                    "id": ctx.author.id,
                    "questions": [self.questionnaire_threads[ctx.author.id]["greeting"]],
                    "answers": [],
                    "prompt": smart_qa_first_prompt,
                    "request_usage": 0,
                    "question_counter": 1
                }
            else:
                self.database[user_discriminator] = self.load_database(
                    str(user_id))

            user_reply = smart_qa_user_template.format(ctx.content)

            self.database[user_discriminator]["prompt"].append(
                {"role": "user", "content": user_reply})

            async with ctx.channel.typing():
                raw_response, usage = await generate_conversation(self.database[user_discriminator]["prompt"], model="gpt-3.5-turbo", max_tokens=200, temperature=0.7, return_usage=True)

            # Validate response
            try:
                response_json = json.loads(raw_response)
            except Exception as e:
                last_prompt = self.database[user_discriminator]["prompt"].pop()
                logger.error(
                    f"Failed to parse response JSON: {e}, raw_response=\n{raw_response}\n\nlast_prompt_chunk=\n{last_prompt}\n")
                await ctx.channel.send(f"生成對話時發生錯誤。回傳結果無法解碼成JSON格式\n raw_response=\n{raw_response} \nlast_prompt_chunk=\n{last_prompt}\n")
                return

            if not check_conversation_format(response_json):
                last_prompt = self.database[user_discriminator]["prompt"].pop()
                logger.error(
                    f"Wrong format in JSON:\n{response_json}\nlast_prompt_chunk=\n{last_prompt}\n")
                await ctx.channel.send(f"生成對話時發生錯誤。回傳格式錯誤\n {response_json} \nlast_prompt_chunk=\n{last_prompt}\n")
                return

            # if response_json["question_num"] != self.database[user_discriminator]["question_counter"]+1:
            #     last_prompt = self.database[user_discriminator]["prompt"].pop()
            #     logger.error(
            #         f"Wrong question number:\nresponse_json=\n{response_json}\nlast_prompt_chunk=\n{last_prompt}\n")
            #     await ctx.channel.send(f"生成對話時發生錯誤。回傳的問題編號不正確\n response_json=\n{response_json} \nlast_prompt_chunk=\n{last_prompt}\n")
            #     return

            await ctx.channel.send(response_json["response"])
            logger.info(
                f"\nresponse:\n{json.dumps(response_json, indent=4, ensure_ascii=False)}\n\nUser {user_discriminator} used {usage} tokens in this message.")

            # Save progress
            self.database[user_discriminator]["prompt"].append(
                {"role": "assistant", "content": raw_response})
            self.database[user_discriminator]["questions"].append(
                response_json["response"])
            self.database[user_discriminator]["answers"].append(ctx.content)
            self.database[user_discriminator]["question_counter"] += 1
            self.database[user_discriminator]["request_usage"] += sum(usage)
            self.write_database(user_id, self.database[user_discriminator])

            # Check progress
            if response_json["is_enough"]:
                # If the user has answered all the questions, end the conversation.
                msg = await ctx.channel.send("正在分析您的報告...")

                # Generate report
                user_data, report_usage = await personality_analyze(
                    self.database[user_discriminator]["questions"],
                    self.database[user_discriminator]["answers"],
                    ctx,
                    debug=self.bot.debug,
                    return_usage=True
                )

                if user_data == None:
                    return

                # Send report to user
                report_md = format_report_response(user_data)
                await ctx.author.send(report_md)

                # Save report to database
                self.database[user_discriminator]["report_markdown"] = report_md
                self.database[user_discriminator]["report"] = user_data["report"]
                self.database[user_discriminator]["chat_style"] = user_data["chat_style"]
                self.database[user_discriminator]["background_description"] = user_data["background_description"]
                self.database[user_discriminator]["request_usage"] += sum(
                    report_usage)

                # Save database
                self.write_database(user_id, self.database[user_discriminator])
                with open(os.path.join(self.database_path, f"{user_id}.md"), "w") as f:
                    f.write(report_md)

                await msg.edit(content="已將分析結果私訊給你。即將關閉聊天室！")

                await asyncio.sleep(3)
                del self.questionnaire_threads[ctx.author.id]
                await self.close_thread(ctx.channel.id)

                return

        elif ctx.author.id in self.chatting_threads \
                and ctx.channel.id == self.chatting_threads[ctx.author.id]["thread_id"]:
            # Chatting thread

            conv = self.chatting_threads[ctx.author.id]["conversation"]
            prompt = conv.prepare_prompt(ctx.content)

            if self.bot.debug:
                logger.debug(f"\n\n{conv}\n\n")
                logger.debug(f"Tokens: {num_tokens_from_messages(prompt)}")

            if num_tokens_from_messages(prompt) > 3500:
                await ctx.reply("對話過長，請重新開始對話。")
                del self.chatting_threads[ctx.author.id]
                await self.close_thread(ctx.channel.id)
                return

            try:
                async with ctx.channel.typing():
                    if self.bot.debug:
                        if ctx.content == "掰掰":
                            # Debuging chat exit function
                            full_reply_content = "掰掰"
                        else:
                            # Debuging reply function
                            full_reply_content = "這是一個測試回應。為了避免過度使用 OpenAI API，這個回應是從本地讀取的。"
                    else:
                        start_time = time.time()
                        response = await sync_to_async(openai.ChatCompletion.create)(
                            model="gpt-3.5-turbo",
                            messages=prompt,
                            stream=True
                        )
                        collected_messages = []
                        message = None
                        for chunk in response:
                            chunk_time = time.time() - start_time  # calculate the time delay of the chunk
                            # extract the message
                            chunk_message = chunk['choices'][0]['delta']
                            collected_messages.append(
                                chunk_message)  # save the message
                            if chunk_time > 3.0:
                                full_reply_content = ''.join(
                                    [m.get('content', '') for m in collected_messages])
                                if message:
                                    await message.edit(content=full_reply_content)
                                else:
                                    message = await ctx.channel.send(full_reply_content)
                                start_time = time.time()

                        full_reply_content = ''.join(
                            [m.get('content', '') for m in collected_messages])
                        if message:
                            await message.edit(content=full_reply_content)
                        else:
                            message = await ctx.channel.send(full_reply_content)

            except Exception as e:
                logger.error(f"Failed to generate conversation: {e}")
                await ctx.reply(f"生成對話時發生錯誤：{e}")

            if full_reply_content == "":
                await ctx.reply("沒有生成任何回應。")
                return

            conv.append_response(full_reply_content)

            # If the bot reply with "掰掰", end the conversation
            if "掰掰" in full_reply_content:
                logger.debug("Quitting Chat...")
                await asyncio.sleep(3)
                del self.chatting_threads[ctx.author.id]
                await self.close_thread(ctx.channel.id)

    @commands.command(name="update_psygpt_api_key")
    @commands.has_permissions(administrator=True)
    async def _update_api_key(self, ctx, key):
        if key is None:
            return
        await ctx.defer()
        openai.api_key = key
        await ctx.send(f"Updated OpenAI API key")

    @commands.hybrid_command(name="analyze", description="Analyze your personality.")
    async def _analyze(self, ctx):
        await ctx.defer()

        user_id = ctx.author.id
        user_discriminator = ctx.author.name + "#" + ctx.author.discriminator
        logger.info(
            f"User {user_discriminator} ({user_id}) started a new analysis.")

        if str(user_id)+".json" in os.listdir(self.database_path):
            # Send a message contains yes button and no button ask if the user wants to overwrite the data, if user choose yes, then keep the function, if no, return.
            view = View()
            view.add_item(
                Button(label="是", style=discord.ButtonStyle.blurple, emoji="✅"))
            view.add_item(
                Button(label="否", style=discord.ButtonStyle.gray, emoji="❌"))

            message = await ctx.send("是否要覆蓋已記錄的資料？", view=view)

            def check(res):
                return res.data["component_type"] == 2 and res.user.id == ctx.author.id and res.message.id == message.id

            try:
                res = await self.bot.wait_for("interaction", timeout=10.0, check=check)
                custom_id = res.data["custom_id"]
                clicked_button = None
                for child in view.children:
                    if isinstance(child, Button) and child.custom_id == custom_id:
                        clicked_button = child
                        break
                logger.debug(f"Clicked button: {clicked_button.label}")
                if clicked_button is not None and clicked_button.label == "是":
                    if user_discriminator in self.database:
                        del self.database[user_discriminator]
                    backup_file = os.path.join(
                        self.database_path, "old_"+str(user_id)+".json")
                    if os.path.exists(backup_file):
                        os.remove(backup_file)
                    os.rename(os.path.join(self.database_path,
                              str(user_id)+".json"), backup_file)
                    if user_id in self.questionnaire_threads:
                        del self.questionnaire_threads[user_id]
                    await message.edit(content="資料會在分析完成後覆蓋。", view=None)
                else:
                    await message.edit(content="已取消。", view=None)
                    return
            except asyncio.TimeoutError:
                await message.edit(content="請重新輸入指令。", view=None)
                return

        # Check if the user has already started a conversation in a thread. If yes, send a message that mention the thread to the user.
        if user_id in self.questionnaire_threads:
            thread_id = self.questionnaire_threads[user_id]
            try:
                thread = await self.bot.fetch_channel(thread_id)
            except Exception as e:
                # If the thread has been deleted, remove the thread from the dictionary.
                del self.questionnaire_threads[user_id]
                await ctx.send("請重新開始一次分析。")
                return
            await ctx.send(f"你已經在 <#{thread.id}> 裡面開始了分析。")
            return

        msg = await ctx.send("已開始分析")
        thread = await ctx.channel.create_thread(
            name=f"{ctx.author.name} 的分析", message=msg, auto_archive_duration=60)
        self.questionnaire_threads[user_id] = {
            "thread_id": thread.id,
            "greeting": random.choice(greeting_candidate_list),
        }
        await thread.send(self.questionnaire_threads[user_id]["greeting"])

    @commands.hybrid_command(name="self_chat", description="Chat with you. Yes, you.")
    async def _self_chat(self, ctx):
        await ctx.defer()
        user_id = ctx.author.id
        user_discriminator = ctx.author.name + "#" + ctx.author.discriminator

        if str(user_id)+".json" not in os.listdir(self.database_path):
            await ctx.send("你還沒有進行分析！")
            return

        await ctx.send("WIP...")

        # msg = await ctx.send("已開始分析")
        # thread_name = f"{user_discriminator} 與自己的聊天室"
        # thread = await ctx.channel.create_thread(
        #     name=thread_name,
        #     message=msg,
        #     auto_archive_duration=60,
        # )

        # TODO: Ingect chat prompt
        # conversation = Conversation()
        # conversation.init_system_message(
        #     self.database[user_discriminator]["chat_system_message"])
        # self.chatting_threads[ctx.author.id] = {
        #     "thread_id": thread.id,
        #     "conversation": conversation
        # }

    @commands.hybrid_command(name="report", description="Get your personality report.")
    async def _report(self, ctx):
        """Return the user's personality report by dm."""
        await ctx.defer()

        user_id = ctx.author.id

        if str(user_id)+".json" not in os.listdir(self.database_path):
            await ctx.send("你還沒有進行分析！")
            return

        user_data = self.load_database(user_id)["report_markdown"]

        await ctx.author.send(user_data)

        await ctx.send("已將分析結果私訊給你。")

    async def close_thread(self, id):
        """Delete the thread"""
        try:
            thread = await self.bot.fetch_channel(id)
            await thread.delete()
            return True
        except Exception as e:
            logger.error(f"Failed to close thread {id} with error {e}")
            return False


async def personality_analyze(questions: list, answers: list, ctx, debug: bool = False, return_usage: bool = False):
    """Analyze the user's personality by their answers.

    Args:
        questions (list): A list of questions.
        answers (list): A list of answers.

    Returns:
        string: A string contains the user's personality report.
    """

    # Example to use Conversation and generate_conversation to call OpenAI ChatGPT API.
    prompt = make_report_prompt(questions, answers)

    if not debug:
        raw_response, usage = await generate_conversation(prompt, model="gpt-3.5-turbo", temperature=0.7, max_tokens=1500, return_usage=return_usage)
    else:
        raw_response = "Debug message"

    # Validate response
    try:
        response_json = json.loads(raw_response)
    except Exception as e:
        logger.error(
            f"Failed to parse response JSON: {e}, raw_response: \n{raw_response}\n")
        await ctx.channel.send(f"生成報告時發生錯誤。回傳結果無法解碼成JSON格式\n {response_json} \n")
        return None

    if not check_report_format(response_json):
        logger.error(
            f"Wrong format in JSON: {e}, raw_response: \n{raw_response}\n")
        await ctx.channel.send(f"生成報告時發生錯誤。回傳格式錯誤\n {response_json} \n")
        return None

    return (response_json, usage) if return_usage else response_json


async def setup(client):
    await client.add_cog(PsyGPT(client))
