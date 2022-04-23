import logging
import re
from typing import List

from twitchio.ext import commands

module_logger = logging.getLogger(__name__)

BAN_WORDS = {'viewers', 'followers', 'primes', '(remove the space)', 'mountviewers', 'mystrm', 'famous'}
# TODO: Implement weighted system
# TODO: Read ban words from a structured file
BAN_WORDS_RE = re.compile(r'|'.join(BAN_WORDS), re.IGNORECASE)  # Ban words converted into a regex
IGNORED_SET = re.compile('[\W_]+')  # Regex to match any alphanumeric character
MIN_SCORE = 2  # The minimum score a message needs to hit before getting flagged


class MyBot(commands.Bot):
    def __int__(self, token: str, prefix: str, initial_channels: List[str]):
        commands.Bot.__init__(self, token=token, prefix=prefix, initial_channels=initial_channels)

    async def event_ready(self):
        module_logger.info('Bot is live, logged in as ' + str(self.nick))

    @commands.command()
    async def hello(self, ctx: commands.Context):
        await ctx.send('Hello ' + str(ctx.author.name) + ', I am an automated bot made by nxt__1')

    @commands.command()
    async def leave(self, ctx: commands.Context):
        module_logger.warning('Leave command received, closing')
        if ctx.author.is_broadcaster or ctx.author.is_mod:
            await ctx.send('Hello ' + str(ctx.author.name) + ', I will be leaving your channel now')
        else:
            await ctx.send('Hello ' + str(ctx.author.name) +
                           ', only broadcasters and mods are allowed to use this command')
        await self.close()

    @commands.command()
    async def goal(self, ctx: commands.Context):
        await ctx.send('Hi, I am a bot and for now my only goal is boot pesky spam/phishing bots out of here. Oh, and '
                       'world dominion ofcourse.')

    async def event_message(self, message):
        # Ignore the bots own messages
        if message.echo:
            return

        # Print the contents of our message to console...
        module_logger.debug('Chatter message: ' + message.content)

        # Filter out spaces and non-alpha numeric characters
        filtered_msg = IGNORED_SET.sub('', message.content)
        match = set(re.findall(BAN_WORDS_RE, filtered_msg))
        # if len(match) == 1:
        #     module_logger.info('n_match: ' + str(len(match)) + ': ' + str(match))
        #     await message.channel.send('We can excuse this (' + str(len(match)) + ')')
        if len(match) == 2:
            module_logger.info('n_match: ' + str(len(match)) + ': ' + str(match))
            await message.channel.send('^ We got a bad boy here (' + str(len(match)) + ') (?leave to get rid of me)')
        elif len(match) >= 3:
            module_logger.info('n_match: ' + str(len(match)) + ': ' + str(match))
            await message.channel.send('^ Now this guy just has to go (' + str(len(match)) +
                                       ') (?leave to get rid of me)')

        # Since we have commands and are overriding the default `event_message`
        # We must let the bot know we want to handle and invoke our commands...
        await self.handle_commands(message)
