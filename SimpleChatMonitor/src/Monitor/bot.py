import logging
from typing import List

from twitchio.ext import commands

module_logger = logging.getLogger(__name__)


class MyBot(commands.Bot):
    def __int__(self, token: str, prefix: str, initial_channels: List[str]):
        commands.Bot.__init__(self, token=token, prefix=prefix, initial_channels=initial_channels)

    async def event_ready(self):
        module_logger.info('Bot is live, logged in as ' + str(self.nick))

    @commands.command()
    async def hello(self, ctx: commands.Context):
        await ctx.send('Hello ' + str(ctx.author.name) + ', I am an automated bot made by nxt__1')

    async def event_message(self, message):
        # Ignore the bots own messages
        if message.echo:
            return

        # Print the contents of our message to console...
        module_logger.debug('Chatter message: ' + message.content)

        # Since we have commands and are overriding the default `event_message`
        # We must let the bot know we want to handle and invoke our commands...
        await self.handle_commands(message)
