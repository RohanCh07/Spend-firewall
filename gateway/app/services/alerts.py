"""Budget alerts at 50 / 80 / 100%, deduplicated in Redis per budget window."""

import asyncio
import logging
import smtplib
from email.message import EmailMessage

import httpx
from redis.asyncio import Redis

from app.config import Settings
from app.core.pricing import usd
from app.services.recorder import Recorder
from app.services.tenants import PolicySnap, TenantSnap
from app.storage.redis_store import BudgetSlot

log = logging.getLogger("spendfirewall.alerts")
THRESHOLDS = (50, 80, 100)


class Alerter:
    def __init__(self, redis: Redis, recorder: Recorder, http: httpx.AsyncClient, settings: Settings):
        self.redis = redis
        self.recorder = recorder
        self.http = http
        self.settings = settings
        self._tasks: set[asyncio.Task] = set()

    async def check(self, tenant: TenantSnap, slots: list[tuple[PolicySnap, BudgetSlot]], values: list[int], blocked_index: int | None = None) -> None:
        for i, ((p, slot), v) in enumerate(zip(slots, values)):
            pct = 100 if i == blocked_index else (v * 100 // p.limit_micro if p.limit_micro else 100)
            for t in THRESHOLDS:
                if pct < t:
                    break
                try:
                    first = await self.redis.set(f"sf:alert:{slot.key}:{t}", 1, nx=True, ex=slot.ttl)
                except Exception:  # noqa: BLE001
                    return
                if first:
                    self._fire(tenant, p, slot, t, v)

    def _fire(self, tenant: TenantSnap, p: PolicySnap, slot: BudgetSlot, threshold: int, spent: int) -> None:
        scope_id = slot.scope_id
        self.recorder.alert(tenant_id=tenant.id, policy_id=p.id, scope_id=scope_id, threshold=threshold, spent_micro=spent, limit_micro=p.limit_micro)
        verb = "blocked at" if threshold >= 100 else "reached"
        text = (
            f":rotating_light: Spend Firewall: {p.scope} `{scope_id}` {verb} {threshold}% of budget "
            f"'{p.name}' (${usd(spent):.4f} of ${usd(p.limit_micro):.2f} per {p.window})"
        )
        task = asyncio.create_task(self._send(tenant, text))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _send(self, tenant: TenantSnap, text: str) -> None:
        log.info("alert tenant=%s %s", tenant.id, text)
        if tenant.slack_webhook_url:
            try:
                await self.http.post(tenant.slack_webhook_url, json={"text": text}, timeout=5)
            except httpx.HTTPError as e:
                log.warning("slack alert failed: %s", e)
        if tenant.alert_email and self.settings.smtp_host:
            await asyncio.to_thread(self._email, tenant.alert_email, text)

    def _email(self, to: str, text: str) -> None:
        s = self.settings
        msg = EmailMessage()
        msg["Subject"] = "Spend Firewall budget alert"
        msg["From"] = s.smtp_from
        msg["To"] = to
        msg.set_content(text)
        try:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:  # type: ignore[arg-type]
                smtp.starttls()
                if s.smtp_user:
                    smtp.login(s.smtp_user, s.smtp_password or "")
                smtp.send_message(msg)
        except Exception as e:  # noqa: BLE001
            log.warning("email alert failed: %s", e)
