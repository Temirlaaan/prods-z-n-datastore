"""
Клиент для работы с NetBox API.
"""

import pynetbox
from typing import Optional
from functools import lru_cache

from app.config import (
    NETBOX_URL,
    NETBOX_TOKEN,
    DC_TO_SITE,
    DEVICE_ROLE,
    logger,
)


class NetBoxClient:
    """Клиент для работы с NetBox API."""

    def __init__(self):
        self.api = pynetbox.api(NETBOX_URL, token=NETBOX_TOKEN)
        # Отключаем проверку SSL если нужно
        self.api.http_session.verify = False
        self._sites_cache: dict = {}
        self._manufacturers_cache: dict = {}
        self._device_types_cache: dict = {}
        self._device_role_id: Optional[int] = None

    def test_connection(self) -> bool:
        """Проверка подключения к NetBox."""
        try:
            self.api.status()
            logger.info("Подключение к NetBox успешно")
            return True
        except Exception as e:
            logger.error(f"Ошибка подключения к NetBox: {e}")
            return False

    # =========================================================================
    # Sites
    # =========================================================================

    def get_site_by_name(self, name: str) -> Optional[object]:
        """Получение сайта по имени."""
        if name in self._sites_cache:
            return self._sites_cache[name]

        try:
            sites = self.api.dcim.sites.filter(name=name)
            site = next(iter(sites), None)
            if site:
                self._sites_cache[name] = site
            return site
        except Exception as e:
            logger.error(f"Ошибка получения сайта {name}: {e}")
            return None

    def get_site_for_dc(self, dc_name: str) -> Optional[object]:
        """Получение сайта NetBox для DC из Zabbix."""
        site_name = DC_TO_SITE.get(dc_name)
        if not site_name:
            logger.warning(f"DC {dc_name} не найден в маппинге DC_TO_SITE")
            return None
        return self.get_site_by_name(site_name)

    # =========================================================================
    # Device Role
    # =========================================================================

    def get_or_create_device_role(self) -> Optional[object]:
        """Получение или создание роли устройства Storage."""
        try:
            # Поиск существующей роли
            roles = self.api.dcim.device_roles.filter(slug=DEVICE_ROLE["slug"])
            role = next(iter(roles), None)

            if role:
                logger.debug(f"Роль {DEVICE_ROLE['name']} найдена (id={role.id})")
                return role

            # Создание роли
            role = self.api.dcim.device_roles.create(DEVICE_ROLE)
            logger.info(f"Создана роль {DEVICE_ROLE['name']} (id={role.id})")
            return role
        except Exception as e:
            logger.error(f"Ошибка получения/создания роли: {e}")
            return None

    # =========================================================================
    # Manufacturers
    # =========================================================================

    def get_or_create_manufacturer(self, name: str) -> Optional[object]:
        """Получение или создание производителя."""
        if not name:
            name = "Unknown"

        # Нормализуем имя
        name = name.strip()
        slug = name.lower().replace(" ", "-").replace("_", "-")

        if slug in self._manufacturers_cache:
            return self._manufacturers_cache[slug]

        try:
            # Поиск существующего
            manufacturers = self.api.dcim.manufacturers.filter(slug=slug)
            manufacturer = next(iter(manufacturers), None)

            if manufacturer:
                self._manufacturers_cache[slug] = manufacturer
                return manufacturer

            # Создание нового
            manufacturer = self.api.dcim.manufacturers.create({
                "name": name,
                "slug": slug,
            })
            logger.info(f"Создан производитель {name} (id={manufacturer.id})")
            self._manufacturers_cache[slug] = manufacturer
            return manufacturer
        except Exception as e:
            logger.error(f"Ошибка получения/создания производителя {name}: {e}")
            return None

    # =========================================================================
    # Device Types
    # =========================================================================

    def get_or_create_device_type(
        self,
        model: str,
        manufacturer_name: str,
    ) -> Optional[object]:
        """Получение или создание типа устройства."""
        if not model:
            model = "Unknown Storage"

        # Нормализуем
        model = model.strip()
        slug = model.lower().replace(" ", "-").replace("_", "-")[:50]  # NetBox limit

        cache_key = f"{manufacturer_name}:{slug}"
        if cache_key in self._device_types_cache:
            return self._device_types_cache[cache_key]

        manufacturer = self.get_or_create_manufacturer(manufacturer_name)
        if not manufacturer:
            return None

        try:
            # Поиск существующего
            device_types = self.api.dcim.device_types.filter(
                slug=slug,
                manufacturer_id=manufacturer.id,
            )
            device_type = next(iter(device_types), None)

            if device_type:
                self._device_types_cache[cache_key] = device_type
                return device_type

            # Создание нового
            device_type = self.api.dcim.device_types.create({
                "manufacturer": manufacturer.id,
                "model": model,
                "slug": slug,
            })
            logger.info(f"Создан тип устройства {model} (id={device_type.id})")
            self._device_types_cache[cache_key] = device_type
            return device_type
        except Exception as e:
            logger.error(f"Ошибка получения/создания типа устройства {model}: {e}")
            return None

    # =========================================================================
    # Devices
    # =========================================================================

    def get_device_by_zabbix_id(self, zabbix_hostid: str) -> Optional[object]:
        """Поиск устройства по Zabbix Host ID."""
        try:
            devices = self.api.dcim.devices.filter(
                cf_zabbix_hostid=zabbix_hostid,
            )
            return next(iter(devices), None)
        except Exception as e:
            logger.error(f"Ошибка поиска устройства по zabbix_hostid={zabbix_hostid}: {e}")
            return None

    def get_device_by_id(self, device_id: int) -> Optional[object]:
        """Получение устройства по ID."""
        try:
            return self.api.dcim.devices.get(device_id)
        except Exception as e:
            logger.error(f"Ошибка получения устройства id={device_id}: {e}")
            return None

    def create_device(
        self,
        name: str,
        device_type_id: int,
        site_id: int,
        role_id: int,
        custom_fields: dict = None,
    ) -> Optional[object]:
        """Создание устройства."""
        try:
            data = {
                "name": name,
                "device_type": device_type_id,
                "site": site_id,
                "role": role_id,
                "status": "active",
            }
            if custom_fields:
                data["custom_fields"] = custom_fields

            device = self.api.dcim.devices.create(data)
            logger.info(f"Создано устройство {name} (id={device.id})")
            return device
        except Exception as e:
            logger.error(f"Ошибка создания устройства {name}: {e}")
            return None

    def update_device(
        self,
        device_id: int,
        data: dict,
    ) -> Optional[object]:
        """Обновление устройства."""
        try:
            device = self.api.dcim.devices.get(device_id)
            if not device:
                logger.error(f"Устройство id={device_id} не найдено")
                return None

            device.update(data)
            logger.info(f"Обновлено устройство {device.name} (id={device_id})")
            return device
        except Exception as e:
            logger.error(f"Ошибка обновления устройства id={device_id}: {e}")
            return None

    # =========================================================================
    # IP Addresses
    # =========================================================================

    def get_or_create_ip_address(
        self,
        ip: str,
        device_id: int = None,
    ) -> Optional[object]:
        """Получение или создание IP адреса."""
        if not ip:
            return None

        # Добавляем маску если нет
        if "/" not in ip:
            ip = f"{ip}/32"

        try:
            # Поиск существующего
            ip_addresses = self.api.ipam.ip_addresses.filter(address=ip)
            ip_obj = next(iter(ip_addresses), None)

            if ip_obj:
                return ip_obj

            # Создание нового
            data = {
                "address": ip,
                "status": "active",
            }

            ip_obj = self.api.ipam.ip_addresses.create(data)
            logger.info(f"Создан IP адрес {ip} (id={ip_obj.id})")
            return ip_obj
        except Exception as e:
            logger.error(f"Ошибка получения/создания IP {ip}: {e}")
            return None

    def get_or_create_interface(
        self,
        device_id: int,
        name: str = "mgmt",
    ) -> Optional[object]:
        """Получение или создание интерфейса устройства."""
        try:
            # Поиск существующего интерфейса
            interfaces = self.api.dcim.interfaces.filter(
                device_id=device_id,
                name=name,
            )
            interface = next(iter(interfaces), None)

            if interface:
                return interface

            # Создание нового интерфейса
            interface = self.api.dcim.interfaces.create({
                "device": device_id,
                "name": name,
                "type": "other",  # Management interface
            })
            logger.debug(f"Создан интерфейс {name} для устройства id={device_id}")
            return interface
        except Exception as e:
            logger.error(f"Ошибка создания интерфейса: {e}")
            return None

    def assign_primary_ip(
        self,
        device_id: int,
        ip_address: str,
    ) -> bool:
        """Назначение primary IP устройству через интерфейс."""
        if not ip_address:
            return False

        # Добавляем маску если нет
        if "/" not in ip_address:
            ip_address_with_mask = f"{ip_address}/32"
        else:
            ip_address_with_mask = ip_address

        try:
            device = self.api.dcim.devices.get(device_id)
            if not device:
                return False

            # 1. Создаём или получаем интерфейс
            interface = self.get_or_create_interface(device_id, "mgmt")
            if not interface:
                return False

            # 2. Проверяем, есть ли уже этот IP
            ip_addresses = self.api.ipam.ip_addresses.filter(address=ip_address_with_mask)
            ip_obj = next(iter(ip_addresses), None)

            if ip_obj:
                # IP существует - проверяем привязку
                if ip_obj.assigned_object_id != interface.id:
                    # Перепривязываем к нашему интерфейсу
                    ip_obj.assigned_object_type = "dcim.interface"
                    ip_obj.assigned_object_id = interface.id
                    ip_obj.save()
            else:
                # Создаём IP и сразу привязываем к интерфейсу
                ip_obj = self.api.ipam.ip_addresses.create({
                    "address": ip_address_with_mask,
                    "status": "active",
                    "assigned_object_type": "dcim.interface",
                    "assigned_object_id": interface.id,
                })
                logger.info(f"Создан IP адрес {ip_address_with_mask} (id={ip_obj.id})")

            # 3. Назначаем как primary_ip4
            device.primary_ip4 = ip_obj.id
            device.save()

            logger.debug(f"Назначен primary IP {ip_address} устройству id={device_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка назначения primary IP: {e}")
            return False

    # =========================================================================
    # Custom Fields
    # =========================================================================

    def get_custom_fields(self) -> list:
        """Получение списка custom fields."""
        try:
            return list(self.api.extras.custom_fields.all())
        except Exception as e:
            logger.error(f"Ошибка получения custom fields: {e}")
            return []

    def create_custom_field(self, data: dict) -> Optional[object]:
        """Создание custom field."""
        try:
            cf = self.api.extras.custom_fields.create(data)
            logger.info(f"Создано custom field {data.get('name')} (id={cf.id})")
            return cf
        except Exception as e:
            logger.error(f"Ошибка создания custom field: {e}")
            return None


# Глобальный экземпляр клиента
_netbox_client: Optional[NetBoxClient] = None


def get_netbox_client() -> NetBoxClient:
    """Получение глобального экземпляра клиента NetBox."""
    global _netbox_client
    if _netbox_client is None:
        _netbox_client = NetBoxClient()
    return _netbox_client
