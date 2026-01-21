"""
Клиент для работы с Zabbix API.
"""

import requests
import urllib3
from typing import Optional

from app.config import (
    ZABBIX_URL,
    ZABBIX_USER,
    ZABBIX_PASSWORD,
    ZABBIX_VERIFY_SSL,
    DATASTORE_HOST_GROUPS,
    logger,
)

# Отключение предупреждений SSL если верификация отключена
if not ZABBIX_VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ZabbixClient:
    """Клиент для работы с Zabbix API."""

    def __init__(self):
        self.url = ZABBIX_URL.rstrip("/") + "/api_jsonrpc.php"
        self.auth_token: Optional[str] = None
        self.session = requests.Session()
        self.session.verify = ZABBIX_VERIFY_SSL

    def _request(self, method: str, params: dict) -> dict:
        """Выполнение запроса к Zabbix API."""
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1,
        }

        # Zabbix 7.0+ использует Authorization header вместо параметра auth
        headers = {"Content-Type": "application/json-rpc"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        response = self.session.post(self.url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()

        if "error" in result:
            error = result["error"]
            raise Exception(f"Zabbix API error: {error.get('message', '')} - {error.get('data', '')}")

        return result.get("result", {})

    def login(self) -> bool:
        """Авторизация в Zabbix API."""
        try:
            self.auth_token = self._request(
                "user.login",
                {
                    "username": ZABBIX_USER,
                    "password": ZABBIX_PASSWORD,
                },
            )
            logger.info("Успешная авторизация в Zabbix")
            return True
        except Exception as e:
            logger.error(f"Ошибка авторизации в Zabbix: {e}")
            return False

    def logout(self) -> None:
        """Выход из Zabbix API."""
        # Zabbix 7.0+ не требует явного logout при использовании API токенов
        self.auth_token = None
        logger.debug("Сессия Zabbix закрыта")

    def get_host_groups(self, group_names: list[str]) -> list[dict]:
        """Получение групп хостов по именам."""
        result = self._request(
            "hostgroup.get",
            {
                "output": ["groupid", "name"],
                "filter": {"name": group_names},
            },
        )
        return result

    def get_hosts_by_groups(self, group_names: list[str] = None) -> list[dict]:
        """
        Получение хостов из указанных групп с inventory данными.

        Args:
            group_names: Список имён групп. По умолчанию DATASTORE_HOST_GROUPS.

        Returns:
            Список хостов с их данными.
        """
        if group_names is None:
            group_names = DATASTORE_HOST_GROUPS

        # Получаем ID групп
        groups = self.get_host_groups(group_names)
        if not groups:
            logger.warning(f"Группы не найдены: {group_names}")
            return []

        group_ids = [g["groupid"] for g in groups]
        group_map = {g["groupid"]: g["name"] for g in groups}

        logger.info(f"Найдено {len(groups)} групп: {[g['name'] for g in groups]}")

        # Получаем хосты
        hosts = self._request(
            "host.get",
            {
                "output": ["hostid", "host", "name", "status"],
                "groupids": group_ids,
                "selectGroups": ["groupid", "name"],
                "selectInterfaces": ["ip", "main", "type"],
                "selectInventory": [
                    "name",
                    "os",
                    "serialno_a",
                    "serialno_b",
                    "hardware",
                ],
            },
        )

        # Добавляем информацию о группе DC к каждому хосту
        for host in hosts:
            host["_dc_group"] = None
            for group in host.get("groups", []):
                if group["name"] in group_names:
                    host["_dc_group"] = group["name"]
                    break

        logger.info(f"Получено {len(hosts)} хостов из Zabbix")
        return hosts

    def get_host_primary_ip(self, host: dict) -> Optional[str]:
        """
        Извлечение основного IP адреса хоста.

        Args:
            host: Данные хоста из Zabbix.

        Returns:
            IP адрес или None.
        """
        interfaces = host.get("interfaces", [])

        # Ищем main interface типа agent (type=1)
        for iface in interfaces:
            if iface.get("main") == "1" and iface.get("type") == "1":
                return iface.get("ip")

        # Если нет agent, берём любой main interface
        for iface in interfaces:
            if iface.get("main") == "1":
                return iface.get("ip")

        # Берём первый доступный
        if interfaces:
            return interfaces[0].get("ip")

        return None

    def __enter__(self):
        """Контекстный менеджер: вход."""
        self.login()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Контекстный менеджер: выход."""
        self.logout()
