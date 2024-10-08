import asyncio
import logging
import sys

from Monitor.twitch_bot import TwitchBot
from asynccmd import Cmd

module_logger = logging.getLogger(__name__)


class NxtBot(Cmd):
    def __init__(self, token, own_id: int, prefix, client_secret: str = None, client_id: str = None,
                 loop: asyncio.AbstractEventLoop = None):
        if sys.platform == 'win32':
            mode = "Run"
        else:
            mode = "Reader"
        super().__init__(mode=mode)
        self.intro = 'Welcome to twitchbot shell. Type help or ? to list commands.\n'
        self.prompt = 'bot: '

        # The asyncio event loop that both the Cmd class and TwitchBot class will use
        self.loop = asyncio.AbstractEventLoop = loop or asyncio.get_event_loop()
        self.twitch_bot = TwitchBot(loop=loop, own_token=token, own_id=own_id, client_secret=client_secret,
                                    client_id=client_id, prefix=prefix)

    def run(self):
        # Pass the asyncio loop the Cmd class and start the instance
        super().cmdloop(self.loop)
        sys.stdout.flush()
        # Pass the asyncio loop to the TwitchBot class, and it will start the event loop
        self.twitch_bot.loop.run_until_complete(self.twitch_bot.__ainit__())
        # self.twitch_bot.run()

    def do_say(self, arg):
        try:
            channel_name, message = arg.split(' ', maxsplit=1)
        except ValueError:
            module_logger.warning('Correct usage: say <channel name> <message>')
        else:
            self.loop.create_task(self.twitch_bot.say(channel_name, message))

    def do_gamble(self, arg):
        try:
            channel_name, n_bets = arg.split(' ', maxsplit=1)
        except ValueError:
            module_logger.warning('Correct usage: gamble <channel name> <n_bets>')
        else:
            channel = self.twitch_bot.get_channel(channel_name)
            if channel:
                self.twitch_bot.gamble_bot.start_gamble(channel, int(n_bets, 10))
            else:
                module_logger.error('Channel ' + str(channel_name) + ' not found, make sure the bot has joined the '
                                                                     'channel')
