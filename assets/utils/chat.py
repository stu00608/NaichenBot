import os
import time
import json
import openai
import random
import asyncio
import discord
import tiktoken
import traceback
from datetime import datetime
from collections import deque
from asgiref.sync import sync_to_async

character_info = json.load(
    open("assets/settings/character_info.json", "r", encoding="utf-8"))


class CharacterSelectMenuView(discord.ui.View):
    def __init__(self, author):
        super().__init__()
        self.value = None
        self.author = author

    """Check if the user is the author of the command"""
    async def interaction_check(self, interaction: discord.MessageInteraction) -> bool:
        self.user = interaction.user
        if interaction.user != self.author:
            await interaction.response.send_message(content="僅限發送指令的使用者選擇", ephemeral=True)
            return False
        return True

    """A select menu for the user to choose the character to chat with"""
    @discord.ui.select(
        placeholder="請選擇",
        options=[discord.SelectOption(
            label=character_info[character]["name"],
            value=character,
            description=character_info[character]["description"]) for character in character_info.keys()
        ]
    )
    async def select_callback(self, interaction, select):
        await interaction.response.defer()
        self.value = select.values[0]
        self.stop()


class User:
    def __init__(self, id, conversation_path, debug=False):
        self.id = id
        self.conversation = CharacterConversation(
            id, conversation_path, limit=5, debug=debug)
        self.count = 0

    # These user objects should be accessible by ID, for example if we had a bunch of user
    # objects in a list, and we did `if 1203910293001 in user_list`, it would return True
    # if the user with that ID was in the list
    def __eq__(self, other):
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return f"User(id={self.id}, Conversation={self.conversation})"

    def __str__(self):
        return self.__repr__()


class Conversation:
    """
    A class to store the conversation history. Conversation source should be stored in a folder inside assets/texts.

    Attributes:
    - messages (list): A list of messages for sending api request to OpenAI gpt-3.5-turbo.
    """

    def __init__(self, limit=10, debug=False) -> None:
        self.debug = debug
        # generate random string txt file name
        dummy_file_name = ''.join(random.choices(
            "abcdefghijklmnopqrstuvwxyz", k=10))
        self.log_path = f"assets/logs/conv_history/{dummy_file_name}.txt"
        self.system_messages = None
        self.messages = deque(maxlen=limit)

    def set_log_path(self, path):
        self.log_path = path

    def init_system_message(self, message):
        self.system_messages = {"role": "system", "content": message}
        self._write_log()

    def prepare_prompt(self, prompt):
        '''Get the user input and append it to prompt body. Return the prompt body.'''
        if self.system_messages is None:
            raise Exception("System message not found.")
        self.messages.append({"role": "user", "content": prompt})
        self._write_log()
        return [self.system_messages] + list(self.messages)

    def append_response(self, response):
        '''Get the assistant response and append it to prompt body.'''
        if self.system_messages is None:
            raise Exception("System message not found.")
        self.messages.append({"role": "assistant", "content": response})
        self._write_log()

    def _write_log(self):
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump([self.system_messages] + list(self.messages),
                      f, indent=4, ensure_ascii=False)

    def __len__(self):
        return num_tokens_from_messages(list(self.messages))

    def __repr__(self) -> str:
        return json.dumps(list(self.messages), indent=4, ensure_ascii=False)

    def __str__(self) -> str:
        return json.dumps(list(self.messages), indent=4, ensure_ascii=False)


class CharacterConversation(Conversation):
    """
    A class to store the conversation history. Conversation source should be stored in a folder inside assets/texts.

    Attributes:
    - messages (list): A list of messages for sending api request to OpenAI gpt-3.5-turbo.
    """

    def __init__(self, user, character, limit=10, debug=False) -> None:
        super().__init__(limit, debug)
        label = f"{user}-{character}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.log_path = f"assets/logs/conv_history/{label}.txt"
        self.name = character_info[character]["name"]

        with open(os.path.join(character_info[character]["path"], "intro.txt")) as f:
            self.init_system_message(f.read())
        with open(os.path.join(character_info[character]["path"], "conversation.txt")) as f:
            example_chats = f.read().splitlines()
            for chat in example_chats:
                u, a = chat.split(",", 1)
                self.messages.append(
                    {"role": "user", "content": u.strip("\n")})
                self.messages.append(
                    {"role": "assistant", "content": a.strip("\n")})


def num_tokens_from_messages(messages, model="gpt-3.5-turbo"):
    """Returns the number of tokens used by a list of messages."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    if model == "gpt-3.5-turbo":  # note: future models may deviate from this
        num_tokens = 0
        for message in messages:
            # every message follows <im_start>{role/name}\n{content}<im_end>\n
            num_tokens += 4
            for key, value in message.items():
                num_tokens += len(encoding.encode(value))
                if key == "name":  # if there's a name, the role is omitted
                    num_tokens += -1  # role is always required and always 1 token
        num_tokens += 2  # every reply is primed with <im_start>assistant
        return num_tokens
    else:
        raise NotImplementedError(f"""num_tokens_from_messages() is not presently implemented for model {model}.
See https://github.com/openai/openai-python/blob/main/chatml.md for information on how messages are converted to tokens.""")


async def generate_conversation(prompt: list, model: str = "gpt-3.5-turbo", temperature: float = 0.7, max_tokens: int = 1000, return_usage: bool = False):
    while True:
        try:
            completions = await sync_to_async(openai.ChatCompletion.create)(
                model=model,
                messages=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            break
        except openai.error.RateLimitError as e:
            print("Rate limit reached. Waiting 10 seconds and retry...")
            await asyncio.sleep(10)
        except openai.error.APIError as e:
            print("API error. Waiting 10 seconds and retry...")
            await asyncio.sleep(10)
        except Exception as e:
            print("Unknown error. Waiting 10 seconds and retry...")
            traceback.print_exc()
            return None, None

    response = completions['choices'][0]['message']['content']
    usage = (completions['usage']['prompt_tokens'],
             completions['usage']['completion_tokens'])
    return (response, usage) if return_usage else response
