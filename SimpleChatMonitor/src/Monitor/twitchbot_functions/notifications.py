import json
import logging
import os
from typing import Set

import twitchio
import winotify

from Monitor.Utils import constants

module_logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self):
        self.keywords: Set[str] = set()  # Regex matching all keywords that should trigger a notification
        self.notification_duration = ''  # Duration of notifications, can be 'short' or 'long'

        self.read_config_file(constants.NOTIFICATION_CONFIG_PATH)

    def read_config_file(self, file_path: str) -> None:
        """
        Parses the config file containing the notification configuration.

        :param file_path: Path to the config file
        """

        try:
            with open(os.path.abspath(file_path)) as config_file:
                config_json = json.load(config_file)
        except FileNotFoundError as e:
            module_logger.error('Could not find config file at ' + str(os.path.abspath(file_path)) + ': ' + str(e))
            return
        else:
            self.keywords = set(config_json['keywords'])
            self.notification_duration = config_json['duration']

    def check_message(self, message: twitchio.Message) -> None:
        words = set(str(message.content).lower().split())
        if self.keywords.intersection(words):
            notification = winotify.Notification(app_id='Twitch Bot',
                                                 title=str(message.author.display_name),
                                                 msg=str(message.content),
                                                 duration=self.notification_duration)
            notification.set_audio(winotify.audio.Default, loop=False)
            notification.show()
