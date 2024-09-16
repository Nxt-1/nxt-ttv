import os

# Paths
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_PATH = os.path.abspath('../../Logs')
LOGGING_LEVEL = 'debug'

FILTER_CONFIG_PATH = os.path.abspath('../../bot-filter.json')
AUTH_PATH = os.path.abspath('../../auth.json')
NOTIFICATION_CONFIG_PATH = os.path.abspath('../../notifications.json')
DATABASE_PATH = os.path.abspath('../../database.db')

MINUTES_BEFORE_BAN = 2

# TODO: Integrate this in the channel specific config
SUBS_PER_TICKET = 1
BITS_PER_TICKET = 500
