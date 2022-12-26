"""
Naichen bot main file. This file is the entry point of the bot. 
It will load all extensions in ./cogs/ and start the bot. 
It will also switch avatar to day or night avatar at 06:00 and 18:00. 
The avatar images are stored in ./img/ folder. 
The bot will also change its status to "listening to 後藤さんの呪いだわ..." 
and its activity to "online" when it starts.
"""
import os
import logging
import discord
import argparse
from discord.ext import commands, tasks
from datetime import datetime
import asyncio
import assets.settings.setting as setting

logger = setting.logging.getLogger("bot")
token = os.getenv("BOT_TOKEN")

DAY_TIME = "06:00"
NIGHT_TIME = "18:00"


class Bot(commands.Bot):
    def __init__(self, debug: bool = False):
        self.debug = debug

        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True

        super().__init__(
            command_prefix=commands.when_mentioned_or('!'), 
            intents=intents,
            description="Naichen bot.",
            activity=discord.Activity(type=discord.ActivityType.listening, name="後藤さんの呪いだわ..."),
            status=discord.Status.online
        )

        self.day_avatar = "assets/img/day_bocchi.jpg"
        self.night_avatar = "assets/img/night_bocchi.jpg"
        
        self.init_avatar()

    async def on_ready(self):
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
    
    async def setup_hook(self) -> None:
        """Setup hook for bot startup. This is called before the bot starts the main loop."""
        self.update_avatar.start()
        await load_extensions()
        logger.info("Syncing command to global...")
        cmds = await self.tree.sync()
        logger.info(f"{len(cmds)} commands synced!")

    def switch_avatar(self, is_day: True):
        """Switch avatar to day or night avatar."""
        if is_day:
            with open(self.day_avatar, 'rb') as image:
                asyncio.get_event_loop().create_task(self.user.edit(avatar=image.read()))
                logger.info(f'{self.user} changed its avatar to {self.day_avatar}!')
                self.day_night_state = "day"
        else:
            with open(self.night_avatar, 'rb') as image:
                asyncio.get_event_loop().create_task(self.user.edit(avatar=image.read()))
                logger.info(f'{self.user} changed its avatar to {self.night_avatar}!')
                self.day_night_state = "night"

    def init_avatar(self):
        """Initialize avatar to day or night avatar."""
        now = datetime.now()
        day_time = datetime.strptime(DAY_TIME, "%H:%M")
        night_time = datetime.strptime(NIGHT_TIME, "%H:%M")
        day_time = now.replace(hour=day_time.hour, minute=day_time.minute)
        night_time = now.replace(hour=night_time.hour, minute=night_time.minute)
        if day_time < now < night_time:
            self.day_night_state = "day"
        else:
            self.day_night_state = "night"
        
        

    @tasks.loop(seconds=10)
    async def update_avatar(self):
        """Update avatar to day or night avatar."""
        if bot.is_closed():
            logger.warn(f'{self.user} is offline now!')
            return

        now = datetime.strftime(datetime.now(), '%H:%M')
        if now == DAY_TIME and bot.day_night_state == "night":
            bot.switch_avatar(is_day=True)
        elif now == NIGHT_TIME and bot.day_night_state == "day":
            bot.switch_avatar(is_day=False)


async def load_extensions():
    """Load all extensions in ./cogs/"""
    for f in os.listdir("./cogs"):
	    if f.endswith(".py"):
		    await bot.load_extension("cogs." + f[:-3])

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true', help='Enable debug mode. (Default: False)')
    args = parser.parse_args()

    bot = Bot(debug=args.debug)
    bot.run(token, root_logger=True)