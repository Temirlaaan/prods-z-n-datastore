"""
Главный модуль мониторинга DataStore.

Алгоритм работы:
1. Получить все хосты из Zabbix групп DataStore/*
2. Для каждого хоста:
   - Если нет в NetBox - создать устройство
   - Если есть - сравнить поля и обновить при изменениях
3. Проверить пропавшие устройства (есть в Redis, нет в Zabbix)
4. Отправить уведомления в Telegram
"""

from datetime import datetime
from typing import Optional

from app.config import (
    MISSING_NOTIFY_HOURS,
    MISSING_NOTIFY_REPEAT,
    DRY_RUN,
    logger,
)
from app.zabbix_client import ZabbixClient
from app.netbox_sync import get_netbox_sync
from app.cache import get_cache
from app.notifications import get_notifier
from app.helpers import (
    calculate_hash,
    compare_fields,
    prepare_device_data,
    hours_since,
    now_iso,
)


class DataStoreMonitor:
    """Главный класс мониторинга датасторов."""

    def __init__(self):
        self.cache = get_cache()
        self.sync = get_netbox_sync()
        self.notifier = get_notifier()
        self.stats = {
            "total": 0,
            "new": 0,
            "changed": 0,
            "unchanged": 0,
            "errors": 0,
        }

    def run(self) -> dict:
        """
        Запуск цикла мониторинга.

        Returns:
            Статистика выполнения
        """
        logger.info("=" * 60)
        logger.info("Запуск мониторинга DataStore")
        logger.info("=" * 60)

        if DRY_RUN:
            logger.warning("Режим DRY_RUN: изменения не будут применены")

        # Сбрасываем статистику
        self.stats = {
            "total": 0,
            "new": 0,
            "changed": 0,
            "unchanged": 0,
            "errors": 0,
        }

        try:
            # Получаем хосты из Zabbix
            with ZabbixClient() as zabbix:
                hosts = zabbix.get_hosts_by_groups()

                if not hosts:
                    logger.warning("Нет хостов для обработки")
                    return self.stats

                self.stats["total"] = len(hosts)
                current_hostids = set()

                # Обрабатываем каждый хост
                for host in hosts:
                    hostid = host.get("hostid")
                    current_hostids.add(hostid)

                    primary_ip = zabbix.get_host_primary_ip(host)
                    self._process_host(host, primary_ip)

                # Проверяем пропавшие хосты
                self._check_missing_hosts(current_hostids)

            logger.info("-" * 60)
            logger.info(f"Статистика: всего={self.stats['total']}, "
                       f"новых={self.stats['new']}, "
                       f"изменено={self.stats['changed']}, "
                       f"без изменений={self.stats['unchanged']}, "
                       f"ошибок={self.stats['errors']}")
            logger.info("=" * 60)

        except Exception as e:
            logger.exception(f"Критическая ошибка мониторинга: {e}")
            self.notifier.send_error(f"Критическая ошибка: {e}")

        return self.stats

    def _process_host(self, host: dict, primary_ip: str) -> None:
        """
        Обработка одного хоста.

        Args:
            host: Данные хоста из Zabbix
            primary_ip: Primary IP адрес
        """
        hostid = host.get("hostid")
        name = host.get("name", "Unknown")

        try:
            # Подготавливаем данные
            data = prepare_device_data(host, primary_ip)
            current_hash = calculate_hash(host, primary_ip)

            # Проверяем, был ли хост пропавшим
            missing_since = self.cache.get_missing_since(hostid)
            if missing_since:
                # Хост вернулся!
                hours = hours_since(missing_since)
                logger.info(f"Хост {name} вернулся после {hours:.1f} часов отсутствия")
                self.notifier.send_datastore_returned(data, hours)
                self.cache.clear_missing_since(hostid)
                self.cache.clear_last_notified(hostid)

            # Проверяем, есть ли устройство в NetBox
            netbox_id = self.cache.get_netbox_id(hostid)
            if not netbox_id:
                # Ищем в NetBox по zabbix_hostid
                netbox_id = self.sync.find_device_by_zabbix_id(hostid)

            if netbox_id:
                # Устройство существует - проверяем изменения
                self._handle_existing_device(hostid, netbox_id, data, current_hash)
            else:
                # Новое устройство - создаём
                self._handle_new_device(hostid, data, current_hash)

            # Обновляем last_seen
            self.cache.set_last_seen(hostid)

        except Exception as e:
            logger.error(f"Ошибка обработки хоста {name} (id={hostid}): {e}")
            self.stats["errors"] += 1

    def _handle_new_device(
        self,
        hostid: str,
        data: dict,
        current_hash: str,
    ) -> None:
        """
        Обработка нового устройства.

        Args:
            hostid: ID хоста в Zabbix
            data: Подготовленные данные устройства
            current_hash: Хэш текущего состояния
        """
        name = data.get("name")
        logger.info(f"Новый датастор: {name}")

        # Создаём в NetBox
        netbox_id = self.sync.create_device(data)

        if netbox_id:
            # Сохраняем в кэш
            self.cache.set_netbox_id(hostid, netbox_id)
            self.cache.set_hash(hostid, current_hash)
            self.cache.set_data(hostid, data)

            # Уведомляем
            site_name = self.sync.get_site_name(data.get("dc_group", ""))
            self.notifier.send_new_datastore(data, site_name or "Unknown")

            self.stats["new"] += 1
        else:
            logger.error(f"Не удалось создать устройство {name} в NetBox")
            self.stats["errors"] += 1

    def _handle_existing_device(
        self,
        hostid: str,
        netbox_id: int,
        data: dict,
        current_hash: str,
    ) -> None:
        """
        Обработка существующего устройства.

        Args:
            hostid: ID хоста в Zabbix
            netbox_id: ID устройства в NetBox
            data: Подготовленные данные устройства
            current_hash: Хэш текущего состояния
        """
        name = data.get("name")

        # Получаем предыдущий хэш
        prev_hash = self.cache.get_hash(hostid)

        if prev_hash == current_hash:
            # Нет изменений - только обновляем last_sync
            logger.debug(f"Датастор {name}: без изменений")
            self.sync.update_last_sync(netbox_id)
            self.stats["unchanged"] += 1
            return

        # Есть изменения - определяем какие
        prev_data = self.cache.get_data(hostid) or {}
        changes = compare_fields(prev_data, data)

        if changes:
            logger.info(f"Датастор {name}: изменения - {list(changes.keys())}")

            # Обновляем в NetBox
            if self.sync.update_device(netbox_id, data, changes):
                # Обновляем кэш
                self.cache.set_hash(hostid, current_hash)
                self.cache.set_data(hostid, data)

                # Уведомляем
                self.notifier.send_datastore_changed(data, changes)

                self.stats["changed"] += 1
            else:
                logger.error(f"Не удалось обновить устройство {name} в NetBox")
                self.stats["errors"] += 1
        else:
            # Хэш изменился, но поля не изменились (странно)
            # Просто обновляем кэш
            self.cache.set_hash(hostid, current_hash)
            self.cache.set_data(hostid, data)
            self.sync.update_last_sync(netbox_id)
            self.stats["unchanged"] += 1

    def _check_missing_hosts(self, current_hostids: set) -> None:
        """
        Проверка пропавших хостов.

        Args:
            current_hostids: Множество текущих hostid из Zabbix
        """
        # Получаем все известные hostid из кэша
        known_hostids = self.cache.get_all_known_hostids()

        # Находим пропавшие
        missing_hostids = known_hostids - current_hostids

        for hostid in missing_hostids:
            self._handle_missing_host(hostid)

    def _handle_missing_host(self, hostid: str) -> None:
        """
        Обработка пропавшего хоста.

        Args:
            hostid: ID пропавшего хоста
        """
        data = self.cache.get_data(hostid)
        if not data:
            return

        name = data.get("name", "Unknown")

        # Проверяем, когда хост пропал
        missing_since = self.cache.get_missing_since(hostid)
        if not missing_since:
            # Только что пропал
            self.cache.set_missing_since(hostid)
            missing_since = now_iso()
            logger.warning(f"Датастор {name} пропал из Zabbix")

        # Определяем, нужно ли уведомлять
        hours = hours_since(missing_since)
        last_notified = self.cache.get_last_notified(hostid)
        hours_since_notify = hours_since(last_notified) if last_notified else None

        should_notify = self._should_notify_missing(hours, hours_since_notify)

        if should_notify:
            site_name = self.sync.get_site_name(data.get("dc_group", ""))
            last_seen = self.cache.get_last_seen(hostid) or "Неизвестно"

            self.notifier.send_datastore_missing(
                data,
                hours,
                site_name or "Unknown",
                last_seen,
            )
            self.cache.set_last_notified(hostid)
            logger.info(f"Отправлено уведомление о пропаже {name} ({hours:.1f}ч)")

    def _should_notify_missing(
        self,
        hours_missing: float,
        hours_since_notify: Optional[float],
    ) -> bool:
        """
        Определение, нужно ли отправлять уведомление о пропаже.

        Args:
            hours_missing: Часов с момента пропажи
            hours_since_notify: Часов с последнего уведомления

        Returns:
            True если нужно уведомить
        """
        # Первое уведомление
        if hours_since_notify is None:
            return True

        # Проверяем пороги уведомлений
        for threshold in MISSING_NOTIFY_HOURS:
            if hours_missing >= threshold and hours_since_notify >= threshold:
                return True

        # Повторные уведомления каждые N часов
        if hours_since_notify >= MISSING_NOTIFY_REPEAT:
            return True

        return False


def run_monitoring() -> dict:
    """
    Точка входа для запуска мониторинга.

    Returns:
        Статистика выполнения
    """
    monitor = DataStoreMonitor()
    return monitor.run()


def send_daily_report() -> None:
    """Отправка дневного отчёта."""
    logger.info("Формирование дневного отчёта")

    cache = get_cache()
    notifier = get_notifier()

    # Собираем статистику
    known_hostids = cache.get_all_known_hostids()
    total = len(known_hostids)

    # Пропавшие хосты
    missing_hosts = cache.get_missing_hosts()
    missing_list = []
    for item in missing_hosts:
        data = item.get("data", {})
        missing_since = item.get("missing_since")
        hours = hours_since(missing_since) if missing_since else 0
        missing_list.append({
            "name": data.get("name", "Unknown"),
            "hours": hours,
        })

    # Сортируем по времени отсутствия
    missing_list.sort(key=lambda x: x["hours"], reverse=True)

    # Отправляем отчёт
    # Примечание: new и changed за день требуют отдельного подсчёта
    # Пока отправляем 0 (можно добавить счётчики в Redis)
    notifier.send_daily_report(
        total=total,
        new_count=0,
        changed_count=0,
        missing_list=missing_list,
    )


# Точка входа при запуске как модуля
if __name__ == "__main__":
    run_monitoring()
