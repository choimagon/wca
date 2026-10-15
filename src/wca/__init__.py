"""WCA: list(), frist(), spend() for IMEL contest administration."""

from pathlib import Path
from .client import WCA, WCAAPIError, WCAConfigError, WCAConflictError, WCAError, WCANotFoundError

__version__ = "0.2.0"
__all__ = ["WCA", "configure", "list", "frist", "first", "spend", "WCAError", "WCAAPIError", "WCAConfigError", "WCAConflictError", "WCANotFoundError"]
_default: WCA | None = None


def configure(url: str | None = None, secret_key: str | None = None, *, download_dir: str | Path | None = None, timeout: float = 30) -> WCA:
    """Configure the module client; omitted values come from environment variables."""
    global _default
    _default = WCA(url, secret_key, download_dir=download_dir, timeout=timeout)
    return _default


def _client(secret_key: str | None = None) -> WCA:
    global _default
    if _default is None:
        _default = WCA(secret_key=secret_key)
    elif secret_key is not None:
        _default._set_secret_key(secret_key)
    return _default


def list():
    return _client().list()


def frist(download_dir: str | Path | None = None):
    return _client().frist(download_dir)


def first(secret_key: str | None = None, *, download_dir: str | Path | None = None):
    """Download with an optional admin key; reuse that key for later module calls."""
    return _client(secret_key).first(download_dir=download_dir)


def spend(name: str, value: str | int | float, *, submission_id: str | None = None):
    return _client().spend(name, value, submission_id=submission_id)
