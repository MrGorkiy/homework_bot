import logging
import os
import sys
import time
from http import HTTPStatus
from typing import Union

import requests
from telegram import Bot
from dotenv import load_dotenv

from exceptions import ApiError, TokenError, ParseNoneStatus

load_dotenv()

logging.basicConfig(
    datefmt="%H:%M:%S",
    filename="main.log",
    encoding="UTF-8",
    filemode="a",
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(funcName)s - %(message)s'
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(stream=sys.stdout)
formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s (%(funcName)s | %(lineno)d)"
)
handler.setFormatter(formatter)
logger.addHandler(handler)

PRACTICUM_TOKEN = os.getenv("PRACTICUM_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

RETRY_TIME = 600
ENDPOINT = "https://practicum.yandex.ru/api/user_api/homework_statuses/"
HEADERS = {"Authorization": f"OAuth {PRACTICUM_TOKEN}"}

HOMEWORK_STATUSES = {
    "approved": "Работа проверена: ревьюеру всё понравилось. Ура!",
    "reviewing": "Работа взята на проверку ревьюером.",
    "rejected": "Работа проверена: у ревьюера есть замечания.",
}


def send_message(bot: Bot, message: str):
    """Функция отправляет сообщения в Telegram чат.

    Отправляет сообщение в Telegram чат, определяемый
    переменной окружения TELEGRAM_CHAT_ID

    :param bot: экземпляр класса Bot
    :type bot: telegram.Bot
    :param message: Строка с текстом сообщения
    :type message: str
    """
    bot.send_message(TELEGRAM_CHAT_ID, message)
    logging.info("Сообщение успешно отправлено")


def get_api_answer(current_timestamp: int) -> dict:
    """Делает запрос к API-сервису.

    Функция get_api_answer() делает запрос к единственному эндпоинту
    API-сервиса. В качестве параметра функция получает временную метку.

    :param current_timestamp: unitime - временная метка
    :type current_timestamp: int
    :return: возвращает API запрос преобразовав его из формата JSON к
    типам данных Python.
    :rtype: dict

    :raises ApiError: Возникает ошибка при ошибках обращения к API
    """
    timestamp = current_timestamp or int(time.time())
    params = {"from_date": timestamp}
    homework_statuses = requests.get(ENDPOINT, headers=HEADERS, params=params)
    if homework_statuses.status_code == HTTPStatus.OK:
        return homework_statuses.json()
    elif (homework_statuses.status_code == HTTPStatus.NOT_FOUND
          and HTTPStatus.FOUND):
        raise ApiError
    else:
        raise ApiError


def check_response(response) -> Union[bool, dict]:
    """Проверка API на корректность.

    Функция проверяет ответ API на корректность.
    В качестве параметра функция получает ответ от API, в формате dict.
    Если ответ API соответствует ожиданиям, то
    функция возвращает список домашних работ (он может быть и пустым)

    :param response: Ответ от API в формате dict
    :type response: dict

    :return: Возвратит список домашних работ.
    :rtype: dict

    :raises TokenError: Ошибка в случае некорректности ответа API
    """
    if not response['homeworks']:
        return False
    elif type(response["homeworks"]) != list:
        raise TokenError
    else:
        return response["homeworks"]


def parse_status(homework: dict) -> Union[bool, str]:
    """Функция извлекает информацию о конкретной домашней работе.


    :param homework: Один элемент из списка домашних работ.
    :type homework: dict

    :return: В случае корректности возвращается сообщение, иначе
    булевое значение
    :rtype: bool|str

    :raises ParseNoneStatus: Недокументированный статус домашней работы
    """
    if homework:
        homework_name = homework["homework_name"]
        homework_status = homework["status"]
    else:
        return False

    try:
        verdict = HOMEWORK_STATUSES[homework_status]
    except KeyError:
        raise ParseNoneStatus

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens() -> bool:
    """Функция проверяет доступность обязательных переменных.

    Функция проверяет доступность переменных с токенами в файле .evn
    при его отсутствии, требуется создать, пример в .evn.example.

    :return: если все переменные - возвращает True
    :rtype: bool

    :raises TokenError: Отсутствие обязательной переменной
    """
    try:
        if PRACTICUM_TOKEN:
            pass
        if TELEGRAM_TOKEN:
            pass
        if TELEGRAM_CHAT_ID:
            pass
        else:
            raise TokenError
    except TokenError:
        logger.critical("Отсутствует обязательная переменная! Остановка")
    else:
        return True


def main():
    """Основная логика работы бота.

    Последовательность действий:
        Запрос к API.
        Проверка ответа.
        Если есть обновления — получает статус работы из обновления и
        отправить сообщение в Telegram.
        Ждет некоторое время и делает новый запрос.
    """
    if not check_tokens():
        sys.exit()

    bot = Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())

    api_error = 0

    while True:
        try:
            response = get_api_answer(current_timestamp)

            check = check_response(response)
            if check:
                status_homework = parse_status(check[:-1][0])
                send_message(bot, status_homework)
                logger.info("Сообщение с новым статусом отправлено")

            current_timestamp = response["current_date"]
            time.sleep(RETRY_TIME)

        except ParseNoneStatus as error_status:
            message = (
                f"Сбой в работе, недокументированный статус домашней "
                f"работы, обнаруженный в ответе API: {error_status}"
            )
            logger.error(message)
            send_message(bot, message)
            logger.info("Отправка ошибки ParseNoneStatus")
            time.sleep(RETRY_TIME)
        except TokenError as error_token:
            message = f"Отсутствие ожидаемых ключей от API: {error_token}"
            logger.error(message)
            send_message(bot, message)
            logger.info("Отправка ошибки TokenError")
            time.sleep(RETRY_TIME)
        except ApiError as error_api:
            message = f"Нет доступа к API: {error_api}"
            logger.error(message)
            if api_error == 0:
                send_message(bot, message)
                logger.info("Отправка ошибки ApiError")
                api_error += 1
            time.sleep(RETRY_TIME)
        except Exception as error:
            message = f"Сбой в работе программы: {error}"
            logger.error(message)
            send_message(bot, message)
            logger.info("Отправка непредвиденной ошибки")
            time.sleep(RETRY_TIME)
        else:
            logger.debug("В ответе нет изменений")


if __name__ == "__main__":
    main()
