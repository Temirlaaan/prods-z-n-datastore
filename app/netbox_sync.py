"""
Синхронизация устройств с NetBox.
"""

from typing import Optional
from datetime import datetime

from app.config import DRY_RUN, logger
from app.netbox_client import get_netbox_client
from app.helpers import (
    extract_manufacturer_from_hardware,
    extract_model_from_hardware,
    get_site_name_for_group,
    now_iso,
)


class NetBoxSync:
    """Синхронизация устройств с NetBox."""

    def __init__(self):
        self.client = get_netbox_client()
        self._role_id: Optional[int] = None

    def _get_role_id(self) -> Optional[int]:
        """Получение ID роли Storage (с кэшированием)."""
        if self._role_id is None:
            role = self.client.get_or_create_device_role()
            if role:
                self._role_id = role.id
        return self._role_id

    def create_device(self, data: dict) -> Optional[int]:
        """
        Создание устройства в NetBox.

        Args:
            data: Данные устройства (из helpers.prepare_device_data)

        Returns:
            ID созданного устройства или None
        """
        if DRY_RUN:
            logger.info(f"[DRY_RUN] Создание устройства: {data.get('name')}")
            return None

        name = data.get("name")
        hardware = data.get("hardware", "")
        dc_group = data.get("dc_group", "")
        hostid = data.get("hostid")

        # Определяем производителя и модель
        manufacturer_name = extract_manufacturer_from_hardware(hardware)
        model = extract_model_from_hardware(hardware)

        # Получаем сайт
        site_name = get_site_name_for_group(dc_group)
        if not site_name:
            logger.error(f"Не удалось определить сайт для группы {dc_group}")
            return None

        site = self.client.get_site_by_name(site_name)
        if not site:
            logger.error(f"Сайт {site_name} не найден в NetBox")
            return None

        # Получаем тип устройства
        device_type = self.client.get_or_create_device_type(model, manufacturer_name)
        if not device_type:
            logger.error(f"Не удалось создать тип устройства {model}")
            return None

        # Получаем роль
        role_id = self._get_role_id()
        if not role_id:
            logger.error("Не удалось получить роль Storage")
            return None

        # Custom fields
        custom_fields = {
            "zabbix_hostid": hostid,
            "last_sync": now_iso(),
            "os_version": data.get("os", ""),
            "serial_a": data.get("serial_a", ""),
            "serial_b": data.get("serial_b", ""),
            "hardware_info": hardware,
        }

        # Создаём устройство
        device = self.client.create_device(
            name=name,
            device_type_id=device_type.id,
            site_id=site.id,
            role_id=role_id,
            custom_fields=custom_fields,
        )

        if not device:
            return None

        # Назначаем primary IP
        ip = data.get("ip")
        if ip:
            self.client.assign_primary_ip(device.id, ip)

        logger.info(f"Устройство {name} создано в NetBox (id={device.id})")
        return device.id

    def update_device(self, device_id: int, data: dict, changes: dict) -> bool:
        """
        Обновление устройства в NetBox.

        Args:
            device_id: ID устройства в NetBox
            data: Новые данные устройства
            changes: Словарь изменений

        Returns:
            True если успешно
        """
        if DRY_RUN:
            logger.info(f"[DRY_RUN] Обновление устройства id={device_id}: {changes}")
            return True

        update_data = {"custom_fields": {}}

        # Обновляем имя если изменилось
        if "name" in changes:
            update_data["name"] = data.get("name")

        # Обновляем custom fields
        if "os" in changes:
            update_data["custom_fields"]["os_version"] = data.get("os", "")
        if "serial_a" in changes:
            update_data["custom_fields"]["serial_a"] = data.get("serial_a", "")
        if "serial_b" in changes:
            update_data["custom_fields"]["serial_b"] = data.get("serial_b", "")
        if "hardware" in changes:
            update_data["custom_fields"]["hardware_info"] = data.get("hardware", "")

        # Всегда обновляем last_sync
        update_data["custom_fields"]["last_sync"] = now_iso()

        # Убираем пустые custom_fields
        if not update_data["custom_fields"]:
            del update_data["custom_fields"]

        # Обновляем устройство
        result = self.client.update_device(device_id, update_data)

        # Обновляем IP если изменился
        if "ip" in changes:
            ip = data.get("ip")
            if ip:
                self.client.assign_primary_ip(device_id, ip)

        return result is not None

    def find_device_by_zabbix_id(self, zabbix_hostid: str) -> Optional[int]:
        """
        Поиск устройства по Zabbix Host ID.

        Args:
            zabbix_hostid: ID хоста в Zabbix

        Returns:
            ID устройства в NetBox или None
        """
        device = self.client.get_device_by_zabbix_id(zabbix_hostid)
        return device.id if device else None

    def update_last_sync(self, device_id: int) -> bool:
        """
        Обновление времени последней синхронизации.

        Args:
            device_id: ID устройства в NetBox

        Returns:
            True если успешно
        """
        if DRY_RUN:
            return True

        return self.client.update_device(
            device_id,
            {"custom_fields": {"last_sync": now_iso()}},
        ) is not None

    def get_site_name(self, dc_group: str) -> Optional[str]:
        """
        Получение имени сайта для группы DC.

        Args:
            dc_group: Имя группы Zabbix

        Returns:
            Имя сайта NetBox
        """
        return get_site_name_for_group(dc_group)


# Глобальный экземпляр
_sync: Optional[NetBoxSync] = None


def get_netbox_sync() -> NetBoxSync:
    """Получение глобального экземпляра синхронизатора."""
    global _sync
    if _sync is None:
        _sync = NetBoxSync()
    return _sync
