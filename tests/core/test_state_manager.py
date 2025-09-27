# pyright: reportPrivateUsage=false
from pathlib import Path

import aiofiles
import pytest
import yaml

from src.reposter.core.state_manager import _load_state, _save_state, get_last_post_id, set_last_post_id
from src.reposter.models import State


class TestStateManager:
    @pytest.fixture
    def temp_state_file(self, tmp_path: Path) -> Path:
        return tmp_path / "state.yaml"

    @pytest.mark.asyncio
    async def test_load_state_empty_file(self, temp_state_file: Path):
        """Test loading state from a non-existent file."""
        state = await _load_state(temp_state_file)
        assert state == State.model_validate({})

    @pytest.mark.asyncio
    async def test_load_state_valid_yaml(self, temp_state_file: Path):
        """Test loading state from a valid YAML file."""
        state_data = {"domain1": {"source1": 123}}
        async with aiofiles.open(temp_state_file, "w") as f:
            await f.write(yaml.dump(state_data))

        state = await _load_state(temp_state_file)
        expected_state = State.model_validate(state_data)
        assert state == expected_state

    @pytest.mark.asyncio
    async def test_load_state_invalid_yaml(self, temp_state_file: Path):
        """Test loading state from an invalid YAML file."""
        async with aiofiles.open(temp_state_file, "w") as f:
            await f.write("invalid: [yaml: content")

        state = await _load_state(temp_state_file)
        assert state == State.model_validate({})

    @pytest.mark.asyncio
    async def test_save_state(self, temp_state_file: Path):
        """Test saving state to a file."""
        state = State.model_validate({"domain1": {"source1": 456}})
        await _save_state(state, temp_state_file)

        # Verify the file was created and has the correct content
        assert temp_state_file.exists()
        loaded_state = await _load_state(temp_state_file)
        assert loaded_state == state

    @pytest.mark.asyncio
    async def test_get_last_post_id_not_found(self, temp_state_file: Path):
        """Test getting last post ID when domain/source doesn't exist."""
        # Create a state file with some data
        state_data = {"domain1": {"source1": 123}}
        async with aiofiles.open(temp_state_file, "w") as f:
            await f.write(yaml.dump(state_data))

        post_id = await get_last_post_id("nonexistent_domain", "source1", temp_state_file)
        assert post_id == 0

    @pytest.mark.asyncio
    async def test_get_last_post_id_source_not_found(self, temp_state_file: Path):
        """Test getting last post ID when source doesn't exist for domain."""
        # Create a state file with some data
        state_data = {"domain1": {"source1": 123}}
        async with aiofiles.open(temp_state_file, "w") as f:
            await f.write(yaml.dump(state_data))

        post_id = await get_last_post_id("domain1", "nonexistent_source", temp_state_file)
        assert post_id == 0

    @pytest.mark.asyncio
    async def test_get_last_post_id_found(self, temp_state_file: Path):
        """Test getting last post ID when domain and source exist."""
        # Create a state file with some data
        state_data = {"domain1": {"source1": 789, "source2": 999}}
        async with aiofiles.open(temp_state_file, "w") as f:
            await f.write(yaml.dump(state_data))

        post_id = await get_last_post_id("domain1", "source1", temp_state_file)
        assert post_id == 789

    @pytest.mark.asyncio
    async def test_set_last_post_id_new_domain(self, temp_state_file: Path):
        """Test setting last post ID for a new domain."""
        await set_last_post_id("new_domain", 456, "source1", temp_state_file)

        # Verify the state was saved
        state = await _load_state(temp_state_file)
        assert state.root["new_domain"]["source1"] == 456

    @pytest.mark.asyncio
    async def test_set_last_post_id_existing_domain(self, temp_state_file: Path):
        """Test setting last post ID for an existing domain."""
        # First set an initial value
        await set_last_post_id("existing_domain", 123, "source1", temp_state_file)
        # Then update it
        await set_last_post_id("existing_domain", 789, "source1", temp_state_file)

        # Verify the state was updated
        state = await _load_state(temp_state_file)
        assert state.root["existing_domain"]["source1"] == 789

    @pytest.mark.asyncio
    async def test_set_last_post_id_different_sources(self, temp_state_file: Path):
        """Test setting last post ID for different sources under the same domain."""
        await set_last_post_id("domain1", 111, "source1", temp_state_file)
        await set_last_post_id("domain1", 222, "source2", temp_state_file)

        # Verify both sources were saved
        state = await _load_state(temp_state_file)
        assert state.root["domain1"]["source1"] == 111
        assert state.root["domain1"]["source2"] == 222
