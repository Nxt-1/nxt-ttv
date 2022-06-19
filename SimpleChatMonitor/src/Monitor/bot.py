import asyncio
import logging
import sys

from asynccmd import Cmd
from Monitor.filter_bot import TwitchBot

module_logger = logging.getLogger(__name__)


class NxtBot(Cmd):
    def __init__(self, token, prefix, initial_channels, loop: asyncio.AbstractEventLoop = None):
        if sys.platform == 'win32':
            mode = "Run"
        else:
            mode = "Reader"
        super().__init__(mode=mode)
        self.intro = 'Welcome to twitchbot shell. Type help or ? to list commands.\n'
        self.prompt = 'bot: '

        # The asyncio event loop that both the Cmd class and TwitchBot class will use
        self.loop = asyncio.AbstractEventLoop = loop or asyncio.get_event_loop()

        self.filter_bot = TwitchBot(loop=loop, token=token, prefix=prefix, initial_channels=initial_channels)

    def run(self):
        # Pass the asyncio loop the Cmd class and start the instance
        super().cmdloop(self.loop)
        sys.stdout.flush()
        # Pass the asyncio loop to the TwitchBot class, and it will start the event loop
        self.filter_bot.run()

    def do_say(self, arg):
        try:
            channel_name, message = arg.split(' ', maxsplit=1)
        except ValueError:
            module_logger.warning('Correct usage: say <channel name> <message>')
        else:
            self.loop.create_task(self.filter_bot.say(channel_name, message))
