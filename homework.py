import logging
import os
import sys
import time
from http import HTTPStatus
from typing import Union

import requests
import telegram
from dotenv import load_dotenv

from exceptions import ApiError, TokenError, ParseNoneStatus, TelegramBot

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


def send_message(bot: telegram, message: str):
    """Функция отправляет сообщения в Telegram чат.

    Отправляет сообщение в Telegram чат, определяемый
    переменной окружения TELEGRAM_CHAT_ID

    :param bot: экземпляр класса Bot
    :type bot: telegram.Bot
    :param message: Строка с текстом сообщения
    :type message: str
    """
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.info("Сообщение успешно отправлено")
    except Exception as send_message_error:
        raise TelegramBot('Ошибка отправки сообщения', send_message_error)


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
    if type(current_timestamp) != int and type(current_timestamp) != float:
        timestamp = int(time.time())
        logger.error(f'В функцию {get_api_answer.__name__} передано неверное '
                     f'значение current_timestamp: ({current_timestamp}). '
                     f'Исправляю на текущее время {timestamp}')
    else:
        timestamp = current_timestamp

    params = {"from_date": timestamp}

    try:
        homework_statuses = requests.get(ENDPOINT,
                                         headers=HEADERS,
                                         params=params)
        homework_status_code = homework_statuses.status_code
        if homework_status_code != HTTPStatus.OK:
            if homework_status_code == HTTPStatus.UNAUTHORIZED:
                homework_statuses = homework_statuses.json()
                homework_status_request = (homework_statuses.get(
                    'code') or homework_statuses.get('error'))
                print(homework_statuses)
                raise ApiError(f'Обнаружена ошибка возвращаемая API: '
                               f'{homework_status_request} - '
                               f'{homework_statuses.get("message")}, '
                               f'ответ сервера {homework_status_code}',
                               f'Эндпоинт: {ENDPOINT}, Параметры: {params}'
                               )
            else:
                raise ApiError(f'Ошибка: {homework_statuses.status_code}',
                               HTTPStatus(
                                   homework_statuses.status_code).description,
                               f'Эндпоинт: {ENDPOINT}, Параметры: {params}')
        else:
            homework_statuses = homework_statuses.json()
    except requests.ConnectionError as e:
        error_message = (
            "OOPS!! ошибка соединения. Убедитесь, что вы подключены к "
            "Интернету. Технические подробности приведены ниже.\n", e)
        raise ApiError(error_message)
    except requests.Timeout as e:
        error_message = ("OOPS!! Ошибка тайм-аута", e)
        raise ApiError(error_message)
    except requests.RequestException as e:
        error_message = ("OOPS!! General Error", e)
        raise ApiError(error_message)
    except KeyboardInterrupt:
        error_message = "Кто-то закрыл программу"
        raise ApiError(error_message)
    except Exception as requests_error:
        raise ApiError(
            f'Возникла ошибка при обращении к API [{requests_error}]')
    else:
        return homework_statuses


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
    tokens = {PRACTICUM_TOKEN: 'PRACTICUM_TOKEN',
              TELEGRAM_TOKEN: 'TELEGRAM_TOKEN',
              TELEGRAM_CHAT_ID: 'TELEGRAM_CHAT_ID'}
    try:
        for valid_tokens in tokens:
            if valid_tokens and len(str(valid_tokens)) > 1:
                pass
            else:
                raise TokenError(tokens[valid_tokens])
    except TokenError as token_error:
        logger.critical(f"Отсутствует обязательная переменная: {token_error}.")
    else:
        return True


# flake8: noqa: C901
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

    try:
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
    except telegram.error.Unauthorized as error_authorized:
        logger.critical('Ошибка при авторизация в Telegram', error_authorized)
        sys.exit()
    except Exception as error:
        logger.error('Ошибка инициализации Telegram', error)
        sys.exit()

    current_timestamp = int(time.time())

    api_error = 0

    while True:
        try:
            response = get_api_answer(current_timestamp)

            check = check_response(response)
            if check:
                status_homework = parse_status(check[0])
                send_message(bot, status_homework)
                logger.info("Сообщение с новым статусом отправлено")

            current_timestamp = response["current_date"]
            time.sleep(RETRY_TIME)

        except TelegramBot as telegram_bot_error:
            logger.error("Возникла ошибка с отправкой сообщения:",
                         telegram_bot_error)
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
