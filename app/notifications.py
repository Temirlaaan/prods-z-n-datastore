"""
Telegram уведомления для DataStore Monitor.
"""

import requests
from typing import Optional

from app.config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    DRY_RUN,
    logger,
)
from app.helpers import format_duration_hours


class TelegramNotifier:
    """Отправка уведомлений в Telegram."""

    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"

    def _send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Отправка сообщения в Telegram.

        Args:
            text: Текст сообщения
            parse_mode: Режим парсинга (HTML или Markdown)

        Returns:
            True если успешно
        """
        if DRY_RUN:
            logger.info(f"[DRY_RUN] Telegram сообщение:\n{text}")
            return True

        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram не настроен (нет токена или chat_id)")
            return False

        try:
            response = requests.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                },
                timeout=30,
            )
            response.raise_for_status()

            result = response.json()
            if not result.get("ok"):
                logger.error(f"Telegram API error: {result}")
                return False

            logger.debug("Telegram сообщение отправлено")
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки Telegram: {e}")
            return False

    def send_new_datastore(self, data: dict, site_name: str) -> bool:
        """
        Уведомление о создании нового датастора.

        Args:
            data: Данные датастора
            site_name: Имя сайта

        Returns:
            True если успешно
        """
        text = f"""<b>🆕 Новый датастор добавлен</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
<b>Имя:</b> {data.get('name', 'N/A')}
<b>IP:</b> {data.get('ip', 'N/A')}
<b>Hardware:</b> {data.get('hardware', 'N/A')}
<b>OS:</b> {data.get('os', 'N/A')}
<b>Serial A:</b> {data.get('serial_a', 'N/A')}
<b>Serial B:</b> {data.get('serial_b', 'N/A')}
<b>Site:</b> {site_name}
━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Создано в NetBox"""

        return self._send_message(text)

    def send_datastore_changed(
        self,
        data: dict,
        changes: dict,
    ) -> bool:
        """
        Уведомление об изменениях датастора.

        Args:
            data: Текущие данные датастора
            changes: Словарь изменений {field: (old, new)}

        Returns:
            True если успешно
        """
        changes_text = "\n".join(
            f"• <b>{field}:</b> {old} → {new}"
            for field, (old, new) in changes.items()
        )

        text = f"""<b>🔄 Изменения датастора</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
<b>Имя:</b> {data.get('name', 'N/A')}
<b>IP:</b> {data.get('ip', 'N/A')}

<b>Изменения:</b>
{changes_text}
━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Обновлено в NetBox"""

        return self._send_message(text)

    def send_datastore_missing(
        self,
        data: dict,
        hours: float,
        site_name: str,
        last_seen: str,
    ) -> bool:
        """
        Уведомление о пропаже датастора.

        Args:
            data: Данные датастора
            hours: Часов с момента пропажи
            site_name: Имя сайта
            last_seen: Время последнего появления

        Returns:
            True если успешно
        """
        duration = format_duration_hours(hours)

        text = f"""<b>⚠️ Датастор не отвечает ({duration})</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
<b>Имя:</b> {data.get('name', 'N/A')}
<b>IP:</b> {data.get('ip', 'N/A')}
<b>Site:</b> {site_name}
<b>Последний раз:</b> {last_seen}
━━━━━━━━━━━━━━━━━━━━━━━━━"""

        return self._send_message(text)

    def send_datastore_returned(
        self,
        data: dict,
        hours: float,
    ) -> bool:
        """
        Уведомление о возвращении датастора.

        Args:
            data: Данные датастора
            hours: Часов отсутствия

        Returns:
            True если успешно
        """
        duration = format_duration_hours(hours)

        text = f"""<b>✅ Датастор вернулся</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
<b>Имя:</b> {data.get('name', 'N/A')}
<b>Отсутствовал:</b> {duration}
━━━━━━━━━━━━━━━━━━━━━━━━━"""

        return self._send_message(text)

    def send_daily_report(
        self,
        total: int,
        new_count: int,
        changed_count: int,
        missing_list: list,
    ) -> bool:
        """
        Отправка дневного отчёта.

        Args:
            total: Всего датасторов
            new_count: Новых за период
            changed_count: Изменённых за период
            missing_list: Список пропавших [{name, hours}, ...]

        Returns:
            True если успешно
        """
        missing_count = len(missing_list)

        text = f"""<b>📊 DataStore: Дневной отчёт</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
<b>Всего:</b> {total}
<b>🆕 Новых:</b> {new_count}
<b>🔄 Изменений:</b> {changed_count}
<b>⚠️ Не отвечают:</b> {missing_count}"""

        if missing_list:
            missing_text = "\n".join(
                f"• {item['name']} ({format_duration_hours(item['hours'])})"
                for item in missing_list[:10]  # Ограничиваем до 10
            )
            text += f"""

<b>Не отвечают:</b>
{missing_text}"""

            if len(missing_list) > 10:
                text += f"\n... и ещё {len(missing_list) - 10}"

        text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━"

        return self._send_message(text)

    def send_error(self, error_message: str) -> bool:
        """
        Уведомление об ошибке.

        Args:
            error_message: Текст ошибки

        Returns:
            True если успешно
        """
        text = f"""<b>❌ Ошибка DataStore Monitor</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
{error_message}
━━━━━━━━━━━━━━━━━━━━━━━━━"""

        return self._send_message(text)


# Глобальный экземпляр
_notifier: Optional[TelegramNotifier] = None


def get_notifier() -> TelegramNotifier:
    """Получение глобального экземпляра нотификатора."""
    global _notifier
    if _notifier is None:
        _notifier = TelegramNotifier()
    return _notifier
