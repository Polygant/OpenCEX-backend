from lib.exceptions import BaseError


class BotExitCondition(BaseError):
    code = 'bot_exit_condition'
