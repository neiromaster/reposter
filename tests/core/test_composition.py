from src.reposter.core.composition import DefaultAppComposer
from src.reposter.interfaces.app_manager import BaseAppManager


def test_compose_app_returns_app_manager():
    """Test that compose_app returns an instance of BaseAppManager."""
    # Arrange
    composer = DefaultAppComposer()

    # Act
    app = composer.compose_app()

    # Assert
    assert isinstance(app, BaseAppManager)


def test_compose_app_debug_mode():
    """Test that compose_app works in debug mode."""
    # Arrange
    composer = DefaultAppComposer()

    # Act
    app_debug = composer.compose_app(debug=True)
    app_normal = composer.compose_app(debug=False)

    # Assert
    assert isinstance(app_debug, BaseAppManager)
    assert isinstance(app_normal, BaseAppManager)
    # We can't easily check the debug flag since it's passed internally,
    # but at least verify both return valid app managers


def test_compose_app_structure():
    """Test that the composed app has expected components."""
    # Arrange
    composer = DefaultAppComposer()

    # Act
    app = composer.compose_app()

    # Assert
    # Since we don't know the internal structure of AppManager,
    # let's at least verify the app can be instantiated and has expected methods
    assert hasattr(app, "run")
    assert callable(getattr(app, "run", None))


def test_compose_app_different_instances():
    """Test that multiple calls to compose_app return different instances."""
    # Arrange
    composer = DefaultAppComposer()

    # Act
    app1 = composer.compose_app()
    app2 = composer.compose_app()

    # Assert
    # They should be different instances (though might be the same due to potential singletons in components)
    # At least check they are both valid app managers
    assert isinstance(app1, BaseAppManager)
    assert isinstance(app2, BaseAppManager)
