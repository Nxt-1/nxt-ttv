import json
import logging
import os
import re
from typing import Union, Callable, Coroutine, Optional

from twitchio.ext import commands

from Monitor.Utils import Constants

module_logger = logging.getLogger(__name__)

# TODO: Implement weights on sub/vip/following status
IGNORED_SET = re.compile('[\W_]+')  # Regex to match any alphanumeric character


class MessageChecker:
    CYRILLIC_RE = re.compile(r'[А-Яа-яЁё]+', re.IGNORECASE)  # Regex to match any cyrillic character

    def __init__(self, cyrillics_score: float = None):
        """
        :param cyrillics_score: Score to add in case any cyrillic character is found in the message, None to
        disable (default)
        """

        self.name = 'default'  # Descriptor for the specific filter
        self.flagged_re: dict[str, re.Pattern] = {}
        self.cyrillics_score = cyrillics_score
        self.min_score = 999  # Minimum score required for a message to be flagged

        self.read_config_file(Constants.CONFIG_PATH)

    def read_config_file(self, file_path: str) -> None:
        """
        Parses the config file containing the filter configuration.

        :param file_path: Path to the config file
        """

        try:
            with open(os.path.abspath(file_path)) as config_file:
                config_json = json.load(config_file)
        except FileNotFoundError as e:
            # TODO: Handle config not found
            module_logger.error('Could not find config file at ' + str(os.path.abspath(file_path)) + ': ' + str(e))
        else:
            self.name = config_json['name']
            for tier in config_json['flaggedTiers']:
                module_logger.info('Tier name: ' + str(tier) + ' containing: ' + str(config_json['flaggedTiers'][tier]))
                if config_json['flaggedTiers'][tier]:
                    self.flagged_re[tier] = re.compile(r'|'.join(config_json['flaggedTiers'][tier]), re.IGNORECASE)
                else:
                    module_logger.warning('Skipping tier with empty list')
            self.min_score = config_json['minScore']
            module_logger.info('Min score is ' + str(self.min_score))

    def check_message(self, message: str) -> bool:
        """
        Check the passed message against the loaded filter configuration. If the message gets flagged, True is returned.
        False in all other cases.

        :param message: The message to check
        :return: True is case of flagged messages, False otherwise
        # TODO: Implement a result class containing the filter name, offending keywords and score
        """

        # TODO: Check that the config is loaded?

        # Filter out spaces and non-alpha numeric characters
        filtered_msg = IGNORED_SET.sub('', message)

        message_score = 0
        for (tier, tier_re) in self.flagged_re.items():
            match = set(re.findall(tier_re, filtered_msg))
            tier_score = int(tier, base=10) * len(match)
            message_score += tier_score
        # Only check for cyrillics if enabled
        if self.cyrillics_score:
            if re.findall(MessageChecker.CYRILLIC_RE, message):
                module_logger.warning('Matched cyrillics')
                message_score += self.cyrillics_score

        if message_score >= self.min_score:
            module_logger.info('Message with score ' + str(message_score) + ': ' + str(message))
            return True
        else:
            return False


class MyBot(commands.Bot):
    def __init__(self, token: str, prefix: Union[str, list, tuple, set, Callable, Coroutine], client_secret: str = None,
                 initial_channels: Union[list, tuple, Callable] = None, heartbeat: Optional[float] = 30.0, **kwargs):

        super().__init__(token=token, prefix=prefix, client_secret=client_secret, initial_channels=initial_channels,
                         heartbeat=heartbeat, kwargs=kwargs)

        self.spam_bot_filter = MessageChecker(cyrillics_score=10)

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

    @commands.command()
    async def fp(self, ctx: commands.Context):
        module_logger.warning('False positive was reported')
        await ctx.send('False positive report received, thank you')

    async def event_message(self, message):
        # Ignore the bots own messages
        if message.echo:
            return

        if self.spam_bot_filter.check_message(message.content):
            await message.channel.send('^ This message got detected as a bot (?fp to report a false positive or ?leave '
                                       'to get rid of me) @Nxt__1')

        # Since we have commands and are overriding the default `event_message`
        # We must let the bot know we want to handle and invoke our commands...
        await self.handle_commands(message)
