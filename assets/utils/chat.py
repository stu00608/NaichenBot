import os
import json
import openai
import discord
from collections import deque
from transformers import GPT2TokenizerFast
from asgiref.sync import sync_to_async

tokenizer = GPT2TokenizerFast.from_pretrained("gpt2")

character_info = json.load(open("assets/settings/character_info.json", "r", encoding="utf-8"))

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
        options = [discord.SelectOption(
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
    def __init__(self, id, conversation_path):
        self.id = id
        self.history = Conversation(conversation_path, 5)
        self.count = 0

    # These user objects should be accessible by ID, for example if we had a bunch of user
    # objects in a list, and we did `if 1203910293001 in user_list`, it would return True
    # if the user with that ID was in the list
    def __eq__(self, other):
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return f"User(id={self.id}, history={self.history})"

    def __str__(self):
        return self.__repr__()

class Conversation:
    """A class to store the conversation history. Conversation source should be stored in a folder inside assets/texts."""
    def __init__(self, character, limit=5) -> None:
        with open(os.path.join(character["path"], "intro.txt")) as f:
            self.intro = f.read()
        with open(os.path.join(character["path"], "conversation.txt")) as f:
            self.prior_conv = f.read()
        
        self.conv = deque(maxlen=limit)
        self.character = character
        self.name = character["name"]
    
    def render(self):
        active_conv = ""
        for p, c in self.conv:
            active_conv += f"人類: {p}\n{self.name}: {c}\n"
        return self.intro + self.prior_conv + active_conv
    
    def prepare_prompt(self, prompt):
        return self.render() + f"人類: {prompt}\n{self.name}: "
    
    def append_conversation(self, prompt, message):
        self.conv.append((prompt, message))
    
    def __len__(self):
        return get_token_len(self.render())
    
    def __repr__(self) -> str:
        return self.render()
    
    def __str__(self) -> str:
        return self.render()

def get_token_len(text):
    return len(tokenizer(text)["input_ids"])
        
async def generate_conversation(prompt):
    """
    Requests a completion from the OpenAI Text-DaVinci-002 model and returns the completion as a string.

    Parameters:
    - prompt (str): The prompt for which to generate a completion.

    Returns:
    - completion (str): The completion generated by the model.
    """
    completions = await sync_to_async(openai.Completion.create)(
        engine="text-davinci-003",
        prompt=prompt,
        max_tokens=150,
        temperature=0.9,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0.6,
        stop=["\n", " 人類:"]
    )
    message = completions.choices[0].text
    return message