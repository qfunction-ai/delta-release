def to_pascal_case(snake: str) -> str:
    """Convert a snake_case string to PascalCase.

    Example: 'my_tool_name' -> 'MyToolName'
    """
    return "".join(word.capitalize() for word in snake.split("_"))
