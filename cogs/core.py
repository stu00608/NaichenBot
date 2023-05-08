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

    @commands.command(name="delete_all_threads")
    @commands.has_permissions(administrator=True)
    async def _delete_all_threads(self, ctx):
        try:
            for thread in ctx.channel.threads:
                await thread.delete()
            logger.debug("Deleted all threads.")
            await ctx.send("成功刪除所有討論串！")
            return True
        except Exception as e:
            logger.error(f"Failed to delete all threads: {e}")
            await ctx.send(f"刪除討論串時發生錯誤：{e}")
            return False


async def setup(client):
    await client.add_cog(Core(client))
