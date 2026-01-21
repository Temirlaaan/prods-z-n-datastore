"""
Вспомогательные функции для DataStore Monitor.
"""

import hashlib
import json
import re
from datetime import datetime
from typing import Optional

from app.config import DC_TO_SITE, logger


def get_dc_from_group(group_name: str) -> Optional[str]:
    """
    Извлечение имени DC из группы Zabbix.

    Args:
        group_name: Имя группы (напр. "DataStore/DataCenter/Almaty")

    Returns:
        Имя DC (напр. "Almaty") или None
    """
    if not group_name:
        return None
    parts = group_name.split("/")
    return parts[-1] if parts else None


def get_site_name_for_group(group_name: str) -> Optional[str]:
    """
    Получение имени сайта NetBox для группы Zabbix.

    Args:
        group_name: Имя группы Zabbix

    Returns:
        Имя сайта NetBox или None
    """
    dc_name = get_dc_from_group(group_name)
    if not dc_name:
        return None
    return DC_TO_SITE.get(dc_name)


def calculate_hash(host: dict, primary_ip: str) -> str:
    """
    Вычисление хэша состояния хоста для отслеживания изменений.

    Args:
        host: Данные хоста из Zabbix
        primary_ip: Primary IP адрес

    Returns:
        SHA256 хэш состояния
    """
    inventory = host.get("inventory", {}) or {}

    hash_data = {
        "name": host.get("name", ""),
        "status": str(host.get("status", "")),
        "ip": primary_ip or "",
        "os": inventory.get("os", "") or "",
        "serial_a": inventory.get("serialno_a", "") or "",
        "serial_b": inventory.get("serialno_b", "") or "",
        "hardware": inventory.get("hardware", "") or "",
    }

    return hashlib.sha256(
        json.dumps(hash_data, sort_keys=True).encode()
    ).hexdigest()


def extract_manufacturer_from_hardware(hardware: str) -> str:
    """
    Извлечение производителя из строки hardware.

    Args:
        hardware: Строка с информацией об оборудовании

    Returns:
        Имя производителя
    """
    if not hardware:
        return "Unknown"

    hardware_lower = hardware.lower()

    # Известные производители СХД
    manufacturers = {
        "netapp": "NetApp",
        "huawei": "Huawei",
        "oceanstor": "Huawei",
        "dorado": "Huawei",
        "dell": "Dell",
        "emc": "Dell EMC",
        "compellent": "Dell",
        "equallogic": "Dell",
        "powervault": "Dell",
        "powerstore": "Dell",
        "hp": "HPE",
        "hpe": "HPE",
        "3par": "HPE",
        "nimble": "HPE",
        "primera": "HPE",
        "alletra": "HPE",
        "ibm": "IBM",
        "storwize": "IBM",
        "flashsystem": "IBM",
        "pure": "Pure Storage",
        "purestorage": "Pure Storage",
        "hitachi": "Hitachi",
        "infinidat": "Infinidat",
        "netgear": "NETGEAR",
        "synology": "Synology",
        "qnap": "QNAP",
    }

    for keyword, manufacturer in manufacturers.items():
        if keyword in hardware_lower:
            return manufacturer

    # Попытка извлечь первое слово как производителя
    first_word = hardware.split()[0] if hardware.split() else "Unknown"
    return first_word.capitalize()


def extract_model_from_hardware(hardware: str) -> str:
    """
    Извлечение модели из строки hardware.

    Args:
        hardware: Строка с информацией об оборудовании

    Returns:
        Модель устройства
    """
    if not hardware:
        return "Unknown Storage"

    # Убираем лишние пробелы
    hardware = " ".join(hardware.split())

    # Если строка короткая, используем её как модель
    if len(hardware) <= 50:
        return hardware

    # Иначе берём первые 50 символов
    return hardware[:47] + "..."


def compare_fields(old_data: dict, new_data: dict) -> dict:
    """
    Сравнение полей и возврат изменений.

    Args:
        old_data: Старые данные
        new_data: Новые данные

    Returns:
        Словарь изменений {field: (old_value, new_value)}
    """
    changes = {}

    # Поля для сравнения
    fields = ["name", "ip", "os", "serial_a", "serial_b", "hardware", "status"]

    for field in fields:
        old_val = str(old_data.get(field, "") or "")
        new_val = str(new_data.get(field, "") or "")

        if old_val != new_val:
            changes[field] = (old_val, new_val)

    return changes


def format_duration_hours(hours: float) -> str:
    """
    Форматирование длительности в часах.

    Args:
        hours: Количество часов

    Returns:
        Отформатированная строка
    """
    if hours < 1:
        return f"{int(hours * 60)} мин"
    elif hours < 24:
        return f"{hours:.1f} ч"
    else:
        days = int(hours // 24)
        remaining_hours = hours % 24
        if remaining_hours > 0:
            return f"{days} д {remaining_hours:.0f} ч"
        return f"{days} д"


def now_iso() -> str:
    """Текущее время в ISO формате."""
    return datetime.utcnow().isoformat()


def parse_iso(iso_str: str) -> Optional[datetime]:
    """Парсинг ISO строки в datetime."""
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str)
    except ValueError:
        return None


def hours_since(iso_str: str) -> float:
    """Количество часов с момента времени."""
    dt = parse_iso(iso_str)
    if not dt:
        return 0
    delta = datetime.utcnow() - dt
    return delta.total_seconds() / 3600


def prepare_device_data(host: dict, primary_ip: str) -> dict:
    """
    Подготовка данных устройства из хоста Zabbix.

    Args:
        host: Данные хоста из Zabbix
        primary_ip: Primary IP адрес

    Returns:
        Словарь с подготовленными данными
    """
    inventory = host.get("inventory", {}) or {}

    return {
        "hostid": host.get("hostid"),
        "name": host.get("name", ""),
        "host": host.get("host", ""),
        "status": host.get("status", "0"),
        "ip": primary_ip or "",
        "os": inventory.get("os", "") or "",
        "serial_a": inventory.get("serialno_a", "") or "",
        "serial_b": inventory.get("serialno_b", "") or "",
        "hardware": inventory.get("hardware", "") or "",
        "dc_group": host.get("_dc_group", ""),
    }
