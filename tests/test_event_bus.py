from __future__ import annotations

import asyncio

import pytest

from hyperbot.exchange.event_bus import EventBus, EventEnvelope, EventPriority, EventType, EventPayload


@pytest.mark.asyncio
async def test_event_bus_delivers_and_retries() -> None:
    bus = EventBus()
    seen: list[str] = []

    async def handler(event: EventEnvelope) -> None:
        if not seen:
            seen.append(event.event_type)
            raise RuntimeError("retry")
        seen.append(event.event_type)

    await bus.start()
    bus.subscribe("order.*", handler)
    await bus.publish(EventEnvelope(event_id="1", event_type=EventType.ORDER_FILLED, payload=EventPayload(), priority=EventPriority.HIGH))
    await asyncio.sleep(0.2)
    await bus.stop()

    assert len(seen) == 2
    assert seen[0] == EventType.ORDER_FILLED
    assert seen[1] == EventType.ORDER_FILLED


@pytest.mark.asyncio
async def test_event_bus_processes_higher_priority_first() -> None:
    bus = EventBus()
    seen: list[EventPriority] = []

    async def handler(event: EventEnvelope) -> None:
        seen.append(event.priority)

    await bus.start()
    subscription = bus.subscribe("order.*", handler)
    await bus.publish(EventEnvelope(event_id="low", event_type=EventType.ORDER_FILLED, payload=EventPayload(), priority=EventPriority.LOW))
    await bus.publish(EventEnvelope(event_id="high", event_type=EventType.ORDER_FILLED, payload=EventPayload(), priority=EventPriority.HIGH))
    await asyncio.sleep(0.2)
    await bus.stop()
    subscription.unsubscribe()

    assert seen == [EventPriority.HIGH, EventPriority.LOW]


@pytest.mark.asyncio
async def test_event_bus_subscription_token_unsubscribes() -> None:
    bus = EventBus()
    seen: list[EventType] = []

    async def handler(event: EventEnvelope) -> None:
        seen.append(event.event_type)

    subscription = bus.subscribe("order.*", handler)
    await bus.publish(EventEnvelope(event_id="1", event_type=EventType.ORDER_FILLED, payload=EventPayload(), priority=EventPriority.NORMAL))
    await asyncio.sleep(0.05)
    subscription.unsubscribe()
    await bus.publish(EventEnvelope(event_id="2", event_type=EventType.ORDER_FILLED, payload=EventPayload(), priority=EventPriority.NORMAL))
    await asyncio.sleep(0.1)

    assert seen == [EventType.ORDER_FILLED]
