import asyncio
import os
from pathlib import Path

import aiofiles
import yaml

from ..models.dto import State
from ..utils.log import log


async def _load_state(state_file: Path) -> State:
    """Loads the state from the YAML file."""
    if not await asyncio.to_thread(os.path.exists, state_file):
        return State(root={})
    try:
        async with aiofiles.open(state_file) as f:
            content = await f.read()
            state_data = await asyncio.to_thread(yaml.safe_load, content)
            return State(root=state_data) if state_data else State(root={})
    except (yaml.YAMLError, FileNotFoundError):
        return State(root={})


async def _save_state(state: State, state_file: Path) -> None:
    """Saves the state to the YAML file."""
    async with aiofiles.open(state_file, "w") as f:
        content = await asyncio.to_thread(yaml.dump, state.model_dump(mode="json"), indent=4)
        await f.write(content)


async def get_last_post_id(domain: str, state_file: Path) -> int:
    """Reads the last processed post ID for a specific domain from the state file."""
    log(f"💾 Читаю ID последнего поста для {domain} из {state_file}...", indent=1, padding_top=1)
    state = await _load_state(state_file)
    post_id = state.root.get(domain, 0)
    log(f"✅ ID последнего поста для {domain}: {post_id}", indent=1)
    return post_id


async def set_last_post_id(domain: str, post_id: int, state_file: Path) -> None:
    """Writes the last processed post ID for a specific domain to the state file."""
    log(f"💾 Записываю ID последнего поста для {domain} в {state_file}...", indent=3)
    state = await _load_state(state_file)
    state.root[domain] = post_id
    await _save_state(state, state_file)
    log(f"✅ ID последнего поста для {domain} обновлен: {post_id}", indent=3)