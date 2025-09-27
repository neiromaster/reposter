import asyncio
import os
from pathlib import Path

import aiofiles
import yaml

from ..models import State
from ..utils.log import log


async def _load_state(state_file: Path) -> State:
    """Loads the state from the YAML file."""
    if not await asyncio.to_thread(os.path.exists, state_file):
        return State.model_validate({})
    try:
        async with aiofiles.open(state_file) as f:
            content = await f.read()
            state_data = await asyncio.to_thread(yaml.safe_load, content)
            return State.model_validate(state_data) if state_data else State.model_validate({})
    except (yaml.YAMLError, FileNotFoundError):
        return State.model_validate({})


async def _save_state(state: State, state_file: Path) -> None:
    """Saves the state to the YAML file."""
    async with aiofiles.open(state_file, "w") as f:
        content = await asyncio.to_thread(yaml.dump, state.model_dump(mode="json"), indent=2)
        await f.write(content)


async def get_last_post_id(domain: str, post_source: str, state_file: Path) -> int:
    """Reads the last processed post ID for a specific domain and source from the state file."""
    log(f"💾 Читаю ID последнего поста для {domain} ({post_source}) из {state_file}...", indent=1)
    state = await _load_state(state_file)

    domain_state = state.root.get(domain)
    if domain_state:
        post_id = domain_state.get(post_source, 0)
        log(f"✅ ID последнего поста для {domain} ({post_source}): {post_id}", indent=1)
        return post_id

    log(f"✅ ID последнего поста для {domain} ({post_source}) не найден, возвращаю 0.", indent=1)
    return 0


async def set_last_post_id(domain: str, post_id: int, post_source: str, state_file: Path) -> None:
    """Writes the last processed post ID for a specific domain and source to the state file."""
    log(f"💾 Записываю ID последнего поста для {domain} ({post_source}) в {state_file}...", indent=3, padding_top=1)
    state = await _load_state(state_file)

    if domain not in state.root:
        state.root[domain] = {}

    state.root[domain][post_source] = post_id

    await _save_state(state, state_file)
    log(f"✅ ID последнего поста для {domain} ({post_source}) обновлен: {post_id}", indent=3)
