# Event-Driven Architecture Migration Guide

## Overview

The `AppManager` class has been migrated from a traditional event-based architecture using `asyncio.Event` objects to a modern event-driven architecture using a custom event system.

## Key Changes

### Before: Traditional Event-Based Architecture
- Used direct `asyncio.Event` objects like `_force_run_event`
- Logic was contained in periodic loops with direct method calls
- Synchronization happened through waiting on events

### After: Event-Driven Architecture  
- Uses a custom `EventManager` system for decoupled communication
- Events like `TaskExecutionRequestEvent`, `UserInputReceivedEvent`, etc.
- Event handlers respond to events asynchronously
- Better separation of concerns and modularity

## Event System

The new system includes these events:

- `AppStartEvent` - Emitted when the application starts
- `AppStopEvent` - Emitted when the application stops  
- `TaskExecutionRequestEvent` - Emitted when a task execution is requested
- `TaskExecutionCompleteEvent` - Emitted when a task execution completes
- `HealthCheckRequestEvent` - Emitted when a health check is requested
- `UserInputReceivedEvent` - Emitted when user input is received
- `PeriodicTaskScheduledEvent` - Emitted when a periodic task is scheduled

## Impact on Tests

The old tests in `tests/core/test_app_manager.py` are no longer valid because:
- They depend on internal `asyncio.Event` objects that no longer exist
- The architecture is fundamentally different
- Tests need to verify event emission and handling instead of direct state changes

New tests should focus on:
- Event emission and subscription
- Proper handler responses to events
- Application lifecycle events

## Benefits of New Architecture

1. **Decoupling**: Components no longer need direct references to each other
2. **Extensibility**: Easy to add new event types and handlers
3. **Maintainability**: Clear separation between event producers and consumers
4. **Testability**: Events can be mocked and verified independently
5. **Scalability**: Event-driven systems are more suitable for complex applications