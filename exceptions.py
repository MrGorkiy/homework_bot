class TokenError(Exception):
    """Класс исключений при отсутствии токена"""
    pass


class ApiError(Exception):
    """Класс исключений некорректный в API ответе"""
    pass


class ParseNoneStatus(Exception):
    pass


class TelegramBot(Exception):
    pass