import json
import logging
import os
import re
from typing import Optional

import twitchio
import winotify

from Monitor.Utils import constants

module_logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self):
        self.keywords: Optional[re.Pattern] = None  # Regex matching all keywords that should trigger a notification
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
            # Read the keywords and compile them into one big regex pattern
            self.keywords = r'.*\b(?=' + '|'.join(config_json['keywords']) + r')\b.*'

            self.notification_duration = config_json['duration']

    def check_message(self, message: twitchio.Message) -> None:
        if re.match(self.keywords, str(message.content), re.IGNORECASE):
            notification = winotify.Notification(app_id='Twitch Bot',
                                                 title=str(message.author.display_name),
                                                 msg=str(message.content),
                                                 duration=self.notification_duration)
            notification.set_audio(winotify.audio.Default, loop=False)
            notification.show()
