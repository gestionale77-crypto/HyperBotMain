from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from hyperbot.core.config import Settings
from hyperbot.core.logging import configure_logging


@dataclass(slots=True)
class RuntimeContext:
    settings: Settings
    loop: asyncio.AbstractEventLoop = field(init=False)

    def __post_init__(self) -> None:
        self.loop = asyncio.get_event_loop_policy().get_event_loop()


class HyperBotRuntime:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.logger = configure_logging(self.settings.log_level)
        self.context = RuntimeContext(self.settings)

    async def start(self) -> None:
        self.logger.info("runtime.start", extra={"app": self.settings.app_name})

    async def stop(self) -> None:
        self.logger.info("runtime.stop", extra={"app": self.settings.app_name})
