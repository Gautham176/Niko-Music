from pathlib import Path
from discord.utils import find
import discord
from discord.ext import commands
from discord import Webhook, AsyncWebhookAdapter



class MusicBot(commands.Bot):
    def __init__(self):
        self._cogs = [p.stem for p in Path(".").glob("./bot/cogs/*.py")]
        super().__init__(command_prefix=self.prefix, case_insensitive=True, help_command=None, intents=discord.Intents.all())

    def setup(self):
        print("Running setup...")

        for cog in self._cogs:
            self.load_extension(f"bot.cogs.{cog}")
            print(f" Loaded `{cog}` cog.")

        print("Setup complete.")

    def run(self):
        self.setup()

        TOKEN = "BOT TOKEN"

        print("Running bot...")
        super().run(TOKEN, reconnect=True)

    async def shutdown(self):
        print("Closing connection to Discord...")
        await super().close()

    async def close(self):
        print("Closing on keyboard interrupt...")
        await self.shutdown()

    async def on_connect(self):
        print(f" Connected to Discord (latency: {self.latency*1000:,.0f} ms).")

    async def on_resumed(self):
        print("Bot resumed.")

    async def on_disconnect(self):
        print("Bot disconnected.")

    async def on_error(self, err, *args, **kwargs):
        raise

    async def on_command_error(self, ctx, exc):
        raise getattr(exc, "original", exc)

    async def prefix(self, bot, msg):
        return commands.when_mentioned_or("niko ")(bot, msg)

    async def process_commands(self, msg):
        ctx = await self.get_context(msg, cls=commands.Context)

        if ctx.command is not None:
            await self.invoke(ctx)
     	
    async def on_message(self, msg):
        if not msg.author.bot:
            await self.process_commands(msg)
            
    async def on_ready(bot):
     print(f'Logged in as {bot.user} (ID: {bot.user.id})')
     print('------')
     await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.playing, name=f"niko help in {len(bot.guilds)} servers!"))
     for guild in bot.guilds:
       print(guild.name)
     print("Niko Music is ready.", bot.user)
    
    async def sendToWebhook(content):
     async with aiohttp.ClientSession() as session:
      webhook = Webhook.from_url('WEBHOOKURL',   adapter=AsyncWebhookAdapter(session))
     await webhook.send(content)
    
    async def on_guild_join(bot, guild):
     general = find(lambda x: x.name == 'general',  guild.text_channels)
     if general and general.permissions_for(guild.me).send_messages:
      embed=discord.Embed(description="Thanks for inviting me! Type `niko help` to find out more!")
      await general.send(embed=embed)
      await sendToWebhook(content=f"Niko has just joined `{guild.name}`!! He is now in `{len(bot.guilds)}` servers!")