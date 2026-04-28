"""
Langfuse client initialization and configuration.

This module provides a singleton Langfuse client that can be used throughout
the application for tracing LLM calls and other operations.

Usage:
    from app.core.langfuse_client import langfuse, observe

    # Then use @observe() decorator on functions to trace
"""
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from langfuse import Langfuse, observe

from app.core.config import LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY

# Initialize Langfuse client with environment configuration
langfuse = Langfuse(
    public_key=LANGFUSE_PUBLIC_KEY,
    secret_key=LANGFUSE_SECRET_KEY,
    host=LANGFUSE_HOST,
)

# Track if Langfuse is properly configured
is_configured = bool(LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY)

if not is_configured:
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(
        "[LANGFUSE] Langfuse is not configured. Set LANGFUSE_PUBLIC_KEY and "
        "LANGFUSE_SECRET_KEY environment variables to enable tracing."
    )


F = TypeVar("F", bound=Callable[..., Any])


def traced(
    name: Optional[str] = None,
    as_type: str = "span",
    capture_input: bool = True,
    capture_output: bool = True,
) -> Callable[[F], F]:
    """
    A decorator that adds Langfuse tracing to functions.

    This decorator gracefully handles the case where Langfuse is not configured
    by simply passing through the function without tracing.

    Args:
        name: Custom name for the trace span. Defaults to function name.
        as_type: Type of observation (span, generation, tool, etc.)
        capture_input: Whether to capture function arguments
        capture_output: Whether to capture function return value

    Returns:
        Decorated function with tracing capability
    """
    def decorator(func: F) -> F:
        if not is_configured:
            # Return function unchanged if Langfuse is not configured
            return func

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            return await func(*args, **kwargs)

        # Apply the observe decorator based on whether function is async
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return observe(
                name=name,
                as_type=as_type,
                capture_input=capture_input,
                capture_output=capture_output,
            )(async_wrapper)
        else:
            return observe(
                name=name,
                as_type=as_type,
                capture_input=capture_input,
                capture_output=capture_output,
            )(sync_wrapper)

    return decorator
