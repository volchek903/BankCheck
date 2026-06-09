from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.models import AppState


class JsonStateStorage:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()

    async def load(self) -> AppState:
        async with self._lock:
            if not self._path.exists():
                return AppState()
            raw = self._path.read_text(encoding="utf-8").strip()
            if not raw:
                return AppState()
            return AppState.model_validate(json.loads(raw))

    async def save(self, state: AppState) -> None:
        async with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = state.model_dump(mode="json")
            self._path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
