"""Bounded retries of extraction, never a recursive or autonomous agent loop."""
import time
from urllib.error import HTTPError


def run_with_retries(operation, *, max_attempts, on_attempt=None):
    for attempt in range(1, max_attempts + 1):
        if on_attempt:
            on_attempt(attempt)
        try:
            return operation()
        except PermissionError:
            raise
        except HTTPError as exc:
            if exc.code not in {408, 429, 500, 502, 503, 504} or attempt == max_attempts:
                raise
        except (OSError, ValueError, TypeError, KeyError):
            if attempt == max_attempts:
                raise
        time.sleep(0.1 * attempt)
