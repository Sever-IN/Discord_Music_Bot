import discord
import datetime
from pathlib import Path
from discord.ext import commands


class MyBot(commands.Bot):
    def __init__(self, token: str):
        self._cogs = [p.stem for p in Path(".").glob("./lib/cogs/*")]
        super().__init__(
            command_prefix=self.prefix,
            case_insensitive=True,
            intents=discord.Intents.all(),
            help_command=None
            )

    def setup(self):
        print("Running setup...")

        for cog in self._cogs:
            self.load_extension(f'lib.cogs.{cog}')
            print(f" Loaded `{cog}` cog.")

        print("Setup complete.")

    def run(self):
        self.setup()

        with open("data/tokens/discord.0", "r", encoding="utf-8") as f:
            TOKEN = f.read().split('\n')[0]

        print("Running bot...")
        super().run(TOKEN, reconnect=True)

    async def shutdown(self):
        print("Closing connection to Discord...")
        await super().close()

    async def close(self):
        # channel = self.get_channel(806929965635469352)
        # messages = await channel.history().flatten()
        # await channel.delete_messages(messages)

        print("Closing on keyboard interrupt...")
        await self.shutdown()

    async def on_connect(self):
        print(f" Connected to Discord (latency: {self.latency*1000:,.0f} ms).")

    async def on_resumed(self):
        print("Bot resumed.")

    async def on_disconnect(self):
        print("Bot disconnected.")

    async def on_error(self, err, *args, **kwargs):
        channel = self.get_channel(782997793001177099)
        print(datetime.datetime.now())
        await channel.send(err)
        await channel.send(str(args))
        await channel.send(str(kwargs))

    async def on_command_error(self, ctx, exc):
        raise getattr(exc, "original", exc)

    async def on_ready(self):
        # channel = self.get_channel(806929965635469352)
        # messages = await channel.history().flatten()
        # await channel.delete_messages(messages)
        
        self.client_id = (await self.application_info()).id
        print("Bot ready.")

    async def prefix(self, bot, msg):
        return commands.when_mentioned_or("s!")(bot, msg)

    async def process_commands(self, msg):
        ctx = await self.get_context(msg, cls=commands.Context)

        if ctx.command is not None:
            await self.invoke(ctx)

    async def on_message(self, msg):
        if not msg.author.bot:
            await self.process_commands(msg)