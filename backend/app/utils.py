from fastapi import HTTPException, UploadFile, status

from app.constants import UPLOAD_CHUNK_SIZE


def to_pascal_case(snake: str) -> str:
    """Convert a snake_case string to PascalCase.

    Example: 'my_tool_name' -> 'MyToolName'
    """
    return "".join(word.capitalize() for word in snake.split("_"))


async def read_upload_with_limit(file: UploadFile, max_size: int) -> bytes:
    """Read an uploaded file in chunks, enforcing a maximum size.

    Raises HTTPException(413) if the file exceeds max_size bytes.
    """
    chunks: list[bytes] = []
    total_size = 0
    while True:
        chunk = await file.read(UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Maximum size is {max_size // (1024 * 1024)}MB.",
            )
        chunks.append(chunk)
    return b"".join(chunks)
