"""
Logging and Instrumentation Facility for CrisisOS Switzerland.

This module sets up standardized INFO-level logging and provides decorators
to automatically log all function invocations and their parameters, as well as
specialized logging helpers for GenAI model calls that safely strip heavy inline/binary data.

Use Cases:
1. Intercepting function executions across all API clients to log function names and arguments.
2. Sanitizing parameters so sensitive keys (e.g. passwords, bearer tokens, API keys) are not leaked.
3. Stripping large inline data (base64 images, raw byte arrays) from logs to maintain readability.
4. Logging GenAI calls (model, prompt, configuration) and outputs in accordance with project rules.
"""

import functools
import logging
import sys
from typing import Any, Callable

# Initialize root logger for CrisisOS
logger = logging.getLogger("crisis_data")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def sanitize_value(val: Any, max_len: int = 150) -> Any:
    """
    Sanitize and truncate values to prevent leaking secrets or flooding logs with binary data.

    Parameters:
        val: The object, string, or primitive to sanitize.
        max_len: Maximum length for string representations.

    Returns:
        Sanitized representation safe for logging.
    """
    if isinstance(val, (bytes, bytearray)):
        return f"<bytes: {len(val)} bytes stripped>"
    if isinstance(val, str):
        # Redact obvious token/key patterns
        lower = val.lower()
        if "api-key" in lower or "bearer " in lower:
            return "<REDACTED_SECRET>"
        if len(val) > max_len:
            return f"{val[:max_len]}... [truncated {len(val) - max_len} chars]"
    if isinstance(val, dict):
        sanitized_dict = {}
        for k, v in val.items():
            k_lower = str(k).lower()
            if any(secret_term in k_lower for secret_term in ["key", "token", "password", "secret"]):
                sanitized_dict[k] = "<REDACTED>"
            else:
                sanitized_dict[k] = sanitize_value(v, max_len=60)
        return sanitized_dict
    if isinstance(val, list):
        if len(val) > 5:
            return [sanitize_value(item, max_len=40) for item in val[:5]] + [f"... +{len(val)-5} more"]
        return [sanitize_value(item, max_len=40) for item in val]
    return val


def log_function_call(func: Callable) -> Callable:
    """
    Decorator that logs all function calls at INFO level with their parameters.

    Parameters:
        func: The function to wrap and log.

    Returns:
        Wrapped callable that executes the original function and logs start and completion.
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        sanitized_args = [sanitize_value(a) for a in args]
        sanitized_kwargs = {k: sanitize_value(v) for k, v in kwargs.items()}
        logger.info(
            f"CALL {func.__module__}.{func.__name__} | args={sanitized_args} | kwargs={sanitized_kwargs}"
        )
        try:
            result = func(*args, **kwargs)
            logger.info(f"DONE {func.__module__}.{func.__name__} -> success")
            return result
        except Exception as exc:
            logger.error(f"FAIL {func.__module__}.{func.__name__} -> {type(exc).__name__}: {exc}")
            raise
    return wrapper


def log_genai_call(model: str, prompt: Any, config: dict[str, Any], output: Any) -> None:
    """
    Log GenAI model invocations with model, prompt, config, and output, stripping inline data.

    Parameters:
        model: Identifier of the model used (e.g. 'gemini-2.5-flash').
        prompt: Prompt text, system instructions, or multimodal prompt list.
        config: Generation configuration parameters (temperature, max_tokens, etc.).
        output: Text response or tool calls produced by the model.
    """
    clean_prompt = sanitize_value(prompt, max_len=300)
    clean_output = sanitize_value(output, max_len=300)
    clean_config = sanitize_value(config, max_len=100)
    logger.info(
        f"GENAI INVOCATION | Model: {model} | Config: {clean_config} | Prompt: {clean_prompt} | Output: {clean_output}"
    )
