def log(message: str, indent: int = 0, padding_top: int = 0) -> None:
    """
    Custom print function that supports indentation and top padding.
    """
    for _ in range(padding_top):
        print()
    prefix = "  " * indent

    # Handle encoding issues in Windows console
    output_message = f"{prefix}{message}"
    try:
        print(output_message)
    except UnicodeEncodeError:
        # Fallback to ASCII representation if Unicode fails
        print(output_message.encode("ascii", errors="replace").decode("ascii"))
