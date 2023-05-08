"""
This file contains a cog for the GPT-3 helper commands.
"""

import os
import json
import asyncio
import openai
import discord
from discord.ext import commands
from typing import List, Optional
from collections import deque
from assets.utils.chat import CharacterSelectMenuView, User, Conversation, generate_conversation, num_tokens_from_messages
import assets.settings.setting as setting

character_info = json.load(
    open("assets/settings/character_info.json", "r", encoding="utf-8"))

logger = setting.logging.getLogger("gpt3")

openai.api_key = os.getenv("OPENAI_API_KEY")


class GPT3Helper(commands.Cog):
    """Cog for GPT-3 helper commands. This cog contains commands for generating code and conversation completions.

    Properties:
    - bot (commands.Bot): The bot instance.
    - chatting_users (dict): A dictionary to store the user who is currently chatting in a thread with the bot.
    - chatting_threads (dict): A dictionary to store the thread in which the bot is currently chatting with a user.
    - chat_flag (bool): A flag to indicate whether the chat function in on_message is on or off.
    - conversation (str): The full conversation prompt.
    - content (collections.deque): A deque to store the last 5 messages sent in the chat channel.

    Methods:
    - update_conversation: Update the conversation prompt. Read original conversation material from disk and append conversations from a deque.
    - auto_shutup: A coroutine to turn off the chat function after 10 minutes.

    Commands:
    - update_api_key: Set the OpenAI API key.
    - code: Generate a code completion.
    - chat: Turn on the chat function.
    """

    def __init__(self, bot):
        self.bot = bot

        self.chatting_users = {}
        self.chatting_threads = {}
        self.chatting_start_message = {}

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            # message author is not the bot itself
            return
        if not message.guild:
            # message is from a dm
            return
        if message.author.id in self.chatting_users \
                and message.author.id in self.chatting_threads \
                and message.channel.id == self.chatting_threads[message.author.id]:
            # message is from a chatting user

            user = self.chatting_users[message.author.id]
            prompt = user.conversation.prepare_prompt(message.content)

            if self.bot.debug:
                logger.debug(f"\n\n{user.conversation}\n\n")
                logger.debug(f"Tokens: {num_tokens_from_messages(prompt)}")

            if num_tokens_from_messages(prompt) > 3500:
                await message.reply("對話過長，請重新開始對話。")
                await self.end_conversation(message)
                return

            try:
                async with message.channel.typing():
                    if self.bot.debug:
                        if message.content == "掰掰":
                            # Debuging chat exit function
                            completion = "掰掰"
                        else:
                            # Debuging reply function
                            completion = "這是一個測試回應。為了避免過度使用 OpenAI API，這個回應是從本地讀取的。"
                    else:
                        completion = await generate_conversation(prompt)
            except Exception as e:
                logger.error(f"Failed to generate conversation: {e}")
                await message.reply(f"生成對話時發生錯誤：{e}")

            if completion == "":
                await message.reply("沒有生成任何回應。")
                return

            user.conversation.append_response(completion)
            await message.reply(completion)

            # If the bot reply with "掰掰", end the conversation
            if "掰掰" in completion:
                logger.debug("Quitting Chat...")
                await asyncio.sleep(3)
                await self.end_conversation(message)

    @commands.command(name="update_gpt3_api_key")
    @commands.has_permissions(administrator=True)
    async def _update_api_key(self, ctx, key):
        if key is None:
            return
        await ctx.defer()
        openai.api_key = key
        await ctx.send(f"Updated OpenAI API key")

    @commands.hybrid_command(name="chat", description="開啟一個討論串來和不同角色聊天！")
    async def _chat(self, ctx):
        await ctx.defer()

        if ctx.author.id in self.chatting_users:
            await self.end_conversation(ctx)
            await asyncio.sleep(2)

        # Make a discord select menu view for the user to choose the character to chat with
        view = CharacterSelectMenuView(ctx.author)
        await ctx.send("請選擇一個角色來和他聊天！", view=view)
        await view.wait()
        if view.value == None:
            logger.info("Character selection view timeout")
            return

        logger.debug(
            f"Creating thread to chat with {view.value} for {ctx.author.name}")
        character_name = character_info[view.value]["name"]
        character_greeting = character_info[view.value]["greeting"]

        thread_name = ctx.author.name + f" 與{character_name}的聊天室"
        message_thread = await ctx.channel.send(f"正在創建聊天室...")
        thread = await message_thread.create_thread(
            name=thread_name,
            auto_archive_duration=60,
        )
        await message_thread.edit(content=f"聊天室已創建！")

        self.chatting_users[ctx.author.id] = User(
            ctx.author.id, view.value, debug=self.bot.debug)
        self.chatting_threads[ctx.author.id] = thread.id
        self.chatting_start_message[ctx.author.id] = message_thread

        await thread.send(character_greeting)

    async def close_thread(self, id):
        """Delete the thread"""
        try:
            thread = await self.bot.fetch_channel(id)
            await thread.delete()
            return True
        except Exception as e:
            logger.error(f"Failed to close thread {id} with error {e}")
            return False

    async def end_conversation(self, message):
        if message.author.id in self.chatting_threads:
            thread_id = self.chatting_threads[message.author.id]
            await self.chatting_start_message[message.author.id].edit(content="聊天室已關閉！")

            del self.chatting_start_message[message.author.id]
            del self.chatting_users[message.author.id]
            del self.chatting_threads[message.author.id]
            # Attempt to close and lock the thread.
            await self.close_thread(thread_id)


async def setup(client):
    await client.add_cog(GPT3Helper(client))
