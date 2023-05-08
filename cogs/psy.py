"""
This file contains a cog for AI psychotherapy assistant commands.
"""

import os
import json
import asyncio
import openai
import discord
from discord.ui import View, Button
from discord.ext import commands
from typing import List, Optional
from collections import deque
from assets.utils.chat import User, Conversation, generate_conversation, num_tokens_from_messages
import assets.settings.setting as setting

logger = setting.logging.getLogger("psy")

openai.api_key = os.getenv("OPENAI_API_KEY")


class PsyGPT(commands.Cog):
    """Cog for PsyGPT commands.
    """

    def __init__(self, bot):
        self.bot = bot

        self.database_path = "assets/database/psygpt_database.json"
        self.questions_path = "assets/database/questions.json"

        self.load_database()
        self.load_questions()

        self.chatting_threads = {}

    def load_questions(self):
        if not os.path.exists(self.questions_path):
            logger.error(
                f"Questions file {self.questions_path} does not exist! Make sure you have the file in the correct path.")
            raise FileNotFoundError(
                f"Questions file {self.questions_path} does not exist! Make sure you have the file in the correct path.")
        self.questions = json.load(
            open(self.questions_path, "r", encoding="utf-8"))

    def load_database(self):
        if not os.path.exists(self.database_path):
            logger.info(
                f"Database file {self.database_path} does not exist. Creating one...")
            with open(self.database_path, "w", encoding="utf-8") as f:
                json.dump({}, f)
        self.database = json.load(
            open(self.database_path, "r", encoding="utf-8"))

    def write_database(self):
        json.dump(self.database, open(
            self.database_path, "w", encoding="utf-8"))

    @commands.Cog.listener()
    async def on_message(self, ctx):
        if ctx.author == self.bot.user:
            # message author is not the bot itself
            return
        if not ctx.guild:
            # message is from a dm
            return
        if ctx.author.id in self.chatting_threads \
                and ctx.channel.id == self.chatting_threads[ctx.author.id]["thread_id"]:
            # message is from a chatting user

            # Delete any message inside this thread that is not belong to the bot or the user.
            async for msg in ctx.channel.history(limit=None, oldest_first=True):
                if msg.author.id != ctx.author.id and msg.author.id != self.bot.user.id:
                    await msg.delete()

            user_discriminator = ctx.author.name + "#" + ctx.author.discriminator
            if self.chatting_threads[ctx.author.id]["counter"] == len(self.questions):
                # Make a list of all user messages in this thread in order.
                user_messages = []
                async for msg in ctx.channel.history(limit=None, oldest_first=True):
                    if msg.author.id == ctx.author.id:
                        user_messages.append(msg)

                self.database[user_discriminator] = {
                    "id": ctx.author.id,
                    "questions": self.questions,
                    "answers": [msg.content for msg in user_messages]
                }
                self.write_database()
                # Delete this user in chatting_thread
                del self.chatting_threads[ctx.author.id]

                logger.info(f"Saved user {user_discriminator}'s data.")

                # TODO: Analyze the answers here.

                await ctx.channel.send("分析已完成！將於5秒後自動關閉此討論串。")
                await asyncio.sleep(5)
                await self.close_thread(ctx.channel.id)
            else:
                await ctx.channel.send(self.questions[self.chatting_threads[ctx.author.id]["counter"]])
                self.chatting_threads[ctx.author.id]["counter"] += 1

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
        """
        One user will start from this command to build their personality data. This command will do following things:
        1. Create a thread for the user to answer questions.
        2. Store the answers into a database.
        3. Analyze the answers and store it in the database.
        """
        await ctx.defer()

        user_id = ctx.author.id

        ids_in_database = [self.database[user]["id"] for user in self.database]
        if user_id in ids_in_database:
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
                    await message.edit(content="資料會在分析完成後覆蓋。", view=None)
                else:
                    await message.edit(content="已取消。", view=None)
                    return
            except asyncio.TimeoutError:
                await message.edit(content="請重新輸入指令。", view=None)

        # Check if the user has already started a conversation in a thread. If yes, send a message that mention the thread to the user.
        if user_id in self.chatting_threads:
            thread_id = self.chatting_threads[user_id]
            try:
                thread = await self.bot.fetch_channel(thread_id)
            except Exception as e:
                # If the thread has been deleted, remove the thread from the dictionary.
                del self.chatting_threads[user_id]
                await ctx.send("請重新開始一次分析。")
                return
            await ctx.send(f"你已經在 <#{thread.id}> 裡面開始了分析。")
            return

        thread = await ctx.channel.create_thread(
            name=f"{ctx.author.name} 的分析", auto_archive_duration=60)
        await ctx.send(f"已開始分析，請在 <#{thread.id}> 裡面回答問題。")
        self.chatting_threads[user_id] = {
            "thread_id": thread.id,
            "counter": 0
        }

        await thread.send(self.questions[0])
        self.chatting_threads[user_id]["counter"] += 1

    async def close_thread(self, id):
        """Delete the thread"""
        try:
            thread = await self.bot.fetch_channel(id)
            await thread.delete()
            return True
        except Exception as e:
            logger.error(f"Failed to close thread {id} with error {e}")
            return False


async def setup(client):
    await client.add_cog(PsyGPT(client))
