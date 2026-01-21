#!/usr/bin/env python3
"""
Инициализация NetBox: создание custom fields и роли устройств.

Запускать перед первым использованием мониторинга.
"""

import sys
from app.config import CUSTOM_FIELDS, DEVICE_ROLE, logger
from app.netbox_client import get_netbox_client


def init_custom_fields() -> bool:
    """Создание custom fields в NetBox."""
    client = get_netbox_client()

    logger.info("Проверка/создание custom fields...")

    # Получаем существующие custom fields
    existing_cfs = {cf.name: cf for cf in client.get_custom_fields()}

    success = True
    for name, config in CUSTOM_FIELDS.items():
        if name in existing_cfs:
            logger.info(f"  Custom field '{name}' уже существует")
            continue

        try:
            cf_data = {
                "name": name,
                "type": config.get("type", "text"),
                "label": config.get("label", name),
                "description": config.get("description", ""),
                "required": config.get("required", False),
                "content_types": config.get("content_types", ["dcim.device"]),
            }

            client.create_custom_field(cf_data)
            logger.info(f"  Custom field '{name}' создан")
        except Exception as e:
            logger.error(f"  Ошибка создания custom field '{name}': {e}")
            success = False

    return success


def init_device_role() -> bool:
    """Создание роли устройства Storage."""
    client = get_netbox_client()

    logger.info("Проверка/создание роли устройства Storage...")

    try:
        role = client.get_or_create_device_role()
        if role:
            logger.info(f"  Роль '{DEVICE_ROLE['name']}' готова (id={role.id})")
            return True
        else:
            logger.error("  Не удалось создать роль")
            return False
    except Exception as e:
        logger.error(f"  Ошибка создания роли: {e}")
        return False


def main() -> int:
    """Главная функция инициализации."""
    logger.info("=" * 60)
    logger.info("Инициализация NetBox для DataStore Monitor")
    logger.info("=" * 60)

    client = get_netbox_client()

    # Проверяем подключение
    if not client.test_connection():
        logger.error("Не удалось подключиться к NetBox")
        return 1

    success = True

    # Создаём custom fields
    if not init_custom_fields():
        success = False

    # Создаём роль
    if not init_device_role():
        success = False

    logger.info("=" * 60)
    if success:
        logger.info("Инициализация завершена успешно")
        return 0
    else:
        logger.error("Инициализация завершена с ошибками")
        return 1


if __name__ == "__main__":
    sys.exit(main())
