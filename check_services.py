#!/usr/bin/env python3
"""
Проверка подключения ко всем сервисам.
"""

import sys
from app.config import (
    ZABBIX_URL,
    NETBOX_URL,
    REDIS_HOST,
    REDIS_PORT,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    logger,
)
from app.zabbix_client import ZabbixClient
from app.netbox_client import get_netbox_client
from app.cache import get_cache
from app.notifications import get_notifier


def check_zabbix() -> bool:
    """Проверка подключения к Zabbix."""
    logger.info(f"Проверка Zabbix ({ZABBIX_URL})...")
    try:
        client = ZabbixClient()
        if client.login():
            logger.info("  Zabbix: OK")
            client.logout()
            return True
        else:
            logger.error("  Zabbix: ОШИБКА авторизации")
            return False
    except Exception as e:
        logger.error(f"  Zabbix: ОШИБКА - {e}")
        return False


def check_netbox() -> bool:
    """Проверка подключения к NetBox."""
    logger.info(f"Проверка NetBox ({NETBOX_URL})...")
    try:
        client = get_netbox_client()
        if client.test_connection():
            logger.info("  NetBox: OK")
            return True
        else:
            logger.error("  NetBox: ОШИБКА подключения")
            return False
    except Exception as e:
        logger.error(f"  NetBox: ОШИБКА - {e}")
        return False


def check_redis() -> bool:
    """Проверка подключения к Redis."""
    logger.info(f"Проверка Redis ({REDIS_HOST}:{REDIS_PORT})...")
    try:
        cache = get_cache()
        if cache.test_connection():
            logger.info("  Redis: OK")
            return True
        else:
            logger.error("  Redis: ОШИБКА подключения")
            return False
    except Exception as e:
        logger.error(f"  Redis: ОШИБКА - {e}")
        return False


def check_telegram() -> bool:
    """Проверка настроек Telegram."""
    logger.info("Проверка Telegram...")

    if not TELEGRAM_BOT_TOKEN:
        logger.warning("  Telegram: Токен не настроен")
        return False

    if not TELEGRAM_CHAT_ID:
        logger.warning("  Telegram: Chat ID не настроен")
        return False

    try:
        import requests
        response = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe",
            timeout=10,
        )
        if response.status_code == 200 and response.json().get("ok"):
            bot_info = response.json().get("result", {})
            logger.info(f"  Telegram: OK (бот @{bot_info.get('username', 'unknown')})")
            return True
        else:
            logger.error("  Telegram: Неверный токен")
            return False
    except Exception as e:
        logger.error(f"  Telegram: ОШИБКА - {e}")
        return False


def main() -> int:
    """Главная функция проверки."""
    logger.info("=" * 60)
    logger.info("Проверка подключения к сервисам")
    logger.info("=" * 60)

    results = {
        "Zabbix": check_zabbix(),
        "NetBox": check_netbox(),
        "Redis": check_redis(),
        "Telegram": check_telegram(),
    }

    logger.info("=" * 60)
    logger.info("Результаты:")

    all_ok = True
    for service, status in results.items():
        status_str = "OK" if status else "ОШИБКА"
        logger.info(f"  {service}: {status_str}")
        if not status and service != "Telegram":  # Telegram опционален
            all_ok = False

    logger.info("=" * 60)

    if all_ok:
        logger.info("Все обязательные сервисы доступны")
        return 0
    else:
        logger.error("Некоторые сервисы недоступны")
        return 1


if __name__ == "__main__":
    sys.exit(main())
