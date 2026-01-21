"""
Redis кэш для хранения состояния DataStore Monitor.
"""

import json
from datetime import datetime
from typing import Optional

import redis

from app.config import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_DB,
    REDIS_TTL,
    REDIS_PREFIX,
    logger,
)


class RedisCache:
    """Клиент Redis для хранения состояния мониторинга."""

    def __init__(self):
        self.client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True,
        )
        self.prefix = REDIS_PREFIX
        self.ttl = REDIS_TTL

    def _key(self, hostid: str, suffix: str) -> str:
        """Формирование ключа Redis."""
        return f"{self.prefix}:{hostid}:{suffix}"

    def test_connection(self) -> bool:
        """Проверка подключения к Redis."""
        try:
            self.client.ping()
            logger.info("Подключение к Redis успешно")
            return True
        except Exception as e:
            logger.error(f"Ошибка подключения к Redis: {e}")
            return False

    # =========================================================================
    # Hash (состояние)
    # =========================================================================

    def get_hash(self, hostid: str) -> Optional[str]:
        """Получение хэша состояния хоста."""
        return self.client.get(self._key(hostid, "hash"))

    def set_hash(self, hostid: str, hash_value: str) -> None:
        """Сохранение хэша состояния хоста."""
        self.client.setex(self._key(hostid, "hash"), self.ttl, hash_value)

    # =========================================================================
    # Last seen
    # =========================================================================

    def get_last_seen(self, hostid: str) -> Optional[str]:
        """Получение времени последнего появления хоста."""
        return self.client.get(self._key(hostid, "last_seen"))

    def set_last_seen(self, hostid: str, timestamp: str = None) -> None:
        """Установка времени последнего появления хоста."""
        if timestamp is None:
            timestamp = datetime.utcnow().isoformat()
        self.client.setex(self._key(hostid, "last_seen"), self.ttl, timestamp)

    # =========================================================================
    # Missing since
    # =========================================================================

    def get_missing_since(self, hostid: str) -> Optional[str]:
        """Получение времени пропажи хоста."""
        return self.client.get(self._key(hostid, "missing_since"))

    def set_missing_since(self, hostid: str, timestamp: str = None) -> None:
        """Установка времени пропажи хоста."""
        if timestamp is None:
            timestamp = datetime.utcnow().isoformat()
        self.client.setex(self._key(hostid, "missing_since"), self.ttl, timestamp)

    def clear_missing_since(self, hostid: str) -> None:
        """Очистка времени пропажи хоста (хост вернулся)."""
        self.client.delete(self._key(hostid, "missing_since"))

    # =========================================================================
    # Last notified
    # =========================================================================

    def get_last_notified(self, hostid: str) -> Optional[str]:
        """Получение времени последнего уведомления о пропаже."""
        return self.client.get(self._key(hostid, "last_notified"))

    def set_last_notified(self, hostid: str, timestamp: str = None) -> None:
        """Установка времени последнего уведомления о пропаже."""
        if timestamp is None:
            timestamp = datetime.utcnow().isoformat()
        self.client.setex(self._key(hostid, "last_notified"), self.ttl, timestamp)

    def clear_last_notified(self, hostid: str) -> None:
        """Очистка времени последнего уведомления."""
        self.client.delete(self._key(hostid, "last_notified"))

    # =========================================================================
    # NetBox ID
    # =========================================================================

    def get_netbox_id(self, hostid: str) -> Optional[int]:
        """Получение ID устройства в NetBox."""
        value = self.client.get(self._key(hostid, "netbox_id"))
        return int(value) if value else None

    def set_netbox_id(self, hostid: str, netbox_id: int) -> None:
        """Сохранение ID устройства в NetBox."""
        self.client.setex(self._key(hostid, "netbox_id"), self.ttl, str(netbox_id))

    # =========================================================================
    # Data (полные данные)
    # =========================================================================

    def get_data(self, hostid: str) -> Optional[dict]:
        """Получение сохранённых данных хоста."""
        value = self.client.get(self._key(hostid, "data"))
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        return None

    def set_data(self, hostid: str, data: dict) -> None:
        """Сохранение данных хоста."""
        self.client.setex(
            self._key(hostid, "data"),
            self.ttl,
            json.dumps(data, ensure_ascii=False),
        )

    # =========================================================================
    # Утилиты
    # =========================================================================

    def get_all_known_hostids(self) -> set[str]:
        """Получение всех известных hostid из кэша."""
        pattern = f"{self.prefix}:*:hash"
        hostids = set()

        for key in self.client.scan_iter(pattern):
            # Извлекаем hostid из ключа: datastore:12345:hash -> 12345
            parts = key.split(":")
            if len(parts) >= 2:
                hostids.add(parts[1])

        return hostids

    def delete_host(self, hostid: str) -> None:
        """Удаление всех данных хоста из кэша."""
        suffixes = ["hash", "last_seen", "missing_since", "last_notified", "netbox_id", "data"]
        for suffix in suffixes:
            self.client.delete(self._key(hostid, suffix))

    def get_missing_hosts(self) -> list[dict]:
        """
        Получение списка пропавших хостов.

        Returns:
            Список словарей с информацией о пропавших хостах.
        """
        pattern = f"{self.prefix}:*:missing_since"
        missing = []

        for key in self.client.scan_iter(pattern):
            parts = key.split(":")
            if len(parts) >= 2:
                hostid = parts[1]
                missing_since = self.client.get(key)
                data = self.get_data(hostid)

                missing.append({
                    "hostid": hostid,
                    "missing_since": missing_since,
                    "data": data,
                    "last_notified": self.get_last_notified(hostid),
                })

        return missing


# Глобальный экземпляр кэша
_cache: Optional[RedisCache] = None


def get_cache() -> RedisCache:
    """Получение глобального экземпляра кэша."""
    global _cache
    if _cache is None:
        _cache = RedisCache()
    return _cache
