"""
Core commands cog.
"""

from discord.ext import commands
import assets.settings.setting as setting

logger = setting.logging.getLogger("core")

class Core(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sync")
    @commands.has_permissions(administrator=True)
    async def _sync(self, ctx):
        """Sync commands to current guild."""
        await ctx.defer()
        fmt = await ctx.bot.tree.sync()
        await ctx.send(f"Synced {len(fmt)} commands to current guild.")

async def setup(client):
    await client.add_cog(Core(client))