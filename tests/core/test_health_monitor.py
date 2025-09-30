import asyncio
from typing import Any

import pytest

from src.reposter.core.health_monitor import HealthMonitor


@pytest.fixture
def health_monitor() -> HealthMonitor:
    return HealthMonitor()


async def successful_check() -> dict[str, Any]:
    await asyncio.sleep(0.01)
    return {"status": "ok"}


async def failing_check() -> dict[str, Any]:
    await asyncio.sleep(0.01)
    raise ValueError("Check failed")


@pytest.mark.asyncio
async def test_register_check(health_monitor: HealthMonitor) -> None:
    # Arrange
    assert not health_monitor.checks

    # Act
    health_monitor.register_check("success", successful_check)

    # Assert
    assert "success" in health_monitor.checks
    assert health_monitor.checks["success"] == successful_check


@pytest.mark.asyncio
async def test_check_health_success(health_monitor: HealthMonitor) -> None:
    # Arrange
    health_monitor.register_check("success", successful_check)

    # Act
    results = await health_monitor.check_health()

    # Assert
    assert "success" in results
    assert results["success"] == {"status": "ok"}


@pytest.mark.asyncio
async def test_check_health_failure(health_monitor: HealthMonitor) -> None:
    # Arrange
    health_monitor.register_check("failure", failing_check)

    # Act
    results = await health_monitor.check_health()

    # Assert
    assert "failure" in results
    assert results["failure"]["status"] == "error"
    assert "Check failed" in results["failure"]["message"]


@pytest.mark.asyncio
async def test_check_health_mixed(health_monitor: HealthMonitor) -> None:
    # Arrange
    health_monitor.register_check("success", successful_check)
    health_monitor.register_check("failure", failing_check)

    # Act
    results = await health_monitor.check_health()

    # Assert
    assert "success" in results
    assert results["success"] == {"status": "ok"}
    assert "failure" in results
    assert results["failure"]["status"] == "error"
