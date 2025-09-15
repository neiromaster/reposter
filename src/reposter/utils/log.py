def log(message: str, indent: int = 0, padding_top: int = 0) -> None:
    """
    Custom print function that supports indentation and top padding.
    """
    for _ in range(padding_top):
        print()
    prefix = "  " * indent
    print(f"{prefix}{message}")
