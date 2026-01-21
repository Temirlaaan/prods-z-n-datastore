"""
Конфигурация приложения DataStore Monitor.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# =============================================================================
# Базовые пути
# =============================================================================
BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# =============================================================================
# Zabbix
# =============================================================================
ZABBIX_URL = os.getenv("ZABBIX_URL", "https://zabbix-cloud.ttc.kz/")
ZABBIX_USER = os.getenv("ZABBIX_USER", "")
ZABBIX_PASSWORD = os.getenv("ZABBIX_PASSWORD", "")
ZABBIX_VERIFY_SSL = os.getenv("ZABBIX_VERIFY_SSL", "false").lower() == "true"

# Группы хостов для мониторинга
DATASTORE_HOST_GROUPS = [
    "DataStore/DataCenter/Almaty",
    "DataStore/DataCenter/Astana-Kabanbay",
    "DataStore/DataCenter/Astana-Konaeva",
    "DataStore/DataCenter/Atyrau",
    "DataStore/DataCenter/Karagandy",
]

# =============================================================================
# NetBox
# =============================================================================
NETBOX_URL = os.getenv("NETBOX_URL", "https://web-netbox.t-cloud.kz/")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN", "")

# Маппинг DC из группы Zabbix на Site в NetBox
DC_TO_SITE = {
    "Almaty": "DC Almaty",
    "Astana-Kabanbay": "DC Kabanbay-Batyr28",
    "Astana-Konaeva": "DC Konaeva10",
    "Atyrau": "DC Atyrau",
    "Karagandy": "DC Karaganda",
}

# Device Role для СХД
DEVICE_ROLE = {
    "name": "Storage",
    "slug": "storage",
    "color": "9c27b0",  # фиолетовый
    "description": "Системы хранения данных (СХД)",
}

# Custom Fields для NetBox
CUSTOM_FIELDS = {
    "zabbix_hostid": {
        "type": "text",
        "label": "Zabbix Host ID",
        "description": "ID хоста в Zabbix (ключ связи)",
        "required": False,
        "content_types": ["dcim.device"],
    },
    "last_sync": {
        "type": "text",
        "label": "Last Sync",
        "description": "Время последней синхронизации",
        "content_types": ["dcim.device"],
    },
    "os_version": {
        "type": "text",
        "label": "OS/Firmware Version",
        "description": "Версия прошивки СХД (ONTAP, OceanStor OS, etc.)",
        "content_types": ["dcim.device"],
    },
    "serial_a": {
        "type": "text",
        "label": "Serial Number A",
        "description": "Серийный номер контроллера A",
        "content_types": ["dcim.device"],
    },
    "serial_b": {
        "type": "text",
        "label": "Serial Number B",
        "description": "Серийный номер контроллера B",
        "content_types": ["dcim.device"],
    },
    "hardware_info": {
        "type": "text",
        "label": "Hardware Info",
        "description": "Информация об оборудовании",
        "content_types": ["dcim.device"],
    },
}

# =============================================================================
# Redis
# =============================================================================
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6380"))
REDIS_DB = int(os.getenv("REDIS_DB", "2"))
REDIS_TTL = int(os.getenv("REDIS_TTL", "604800"))  # 7 дней

# Префикс для ключей Redis
REDIS_PREFIX = "datastore"

# =============================================================================
# Telegram
# =============================================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# =============================================================================
# Настройки приложения
# =============================================================================
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
DAILY_REPORT_HOUR = int(os.getenv("DAILY_REPORT_HOUR", "9"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Интервалы уведомлений о пропаже (часы)
MISSING_NOTIFY_HOURS = [0, 1, 6, 24]  # сразу, через 1ч, 6ч, 24ч
MISSING_NOTIFY_REPEAT = 24  # далее каждые 24 часа

# =============================================================================
# Логирование
# =============================================================================
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = LOGS_DIR / "datastore_monitor.log"


def setup_logging() -> logging.Logger:
    """Настройка логирования."""
    logger = logging.getLogger("datastore_monitor")
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    # Консольный handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(console_handler)

    # Файловый handler
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(file_handler)

    return logger


# Создание логгера
logger = setup_logging()
