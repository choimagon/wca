"""Admin-only metadata, download and result operations for contest submissions."""

from __future__ import annotations

import base64
import json
import math
import os
import socket
import ssl
from pathlib import Path
import tempfile
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from uuid import UUID

import certifi

DEFAULT_URL = "https://ufzrasrrhsmkfxribyqp.supabase.co"
_FIELDS = "id,team_name,file_name,file_size,created_at,result"
_MAX_FILE_SIZE = 5 * 1024 * 1024
_PAGE_SIZE = 500


class WCAError(Exception):
    """Base error for WCA operations."""


class WCAConfigError(WCAError, ValueError):
    """Missing or invalid server configuration."""


class WCAAPIError(WCAError):
    """Supabase rejected a request or returned an invalid response."""

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


class WCANotFoundError(WCAError):
    """No matching unprocessed submission exists."""


class WCAConflictError(WCAError):
    """The selected submission was processed or changed before the update."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the admin credential to another endpoint.
        return None


def _validated_key(key: str) -> str:
    if not isinstance(key, str):
        raise WCAConfigError("WCA_SUPABASE_SECRET_KEY에 관리자 비밀 키를 설정해주세요.")
    key = key.strip()
    if key.startswith("sb_secret_") and len(key) >= 25:
        return key
    try:
        payload = key.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError, TypeError):
        claims = {}
    if isinstance(claims, dict) and claims.get("role") == "service_role":
        return key
    raise WCAConfigError("sb_secret_ 비밀 키 또는 service_role 키가 필요합니다. 공개 키로는 관리자 작업을 할 수 없습니다.")


def _name(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 80 or "\0" in value:
        raise ValueError("이름은 1~80자 문자열이어야 합니다.")
    return value.strip()


def _submission_id(value: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("제출 ID는 UUID여야 합니다.") from None


def _result(value: str | int | float) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("결과는 문자열 또는 숫자여야 합니다.")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("결과에 NaN 또는 무한대를 사용할 수 없습니다.")
    result = str(value).strip()
    if not 1 <= len(result) <= 1024 or "\0" in result:
        raise ValueError("결과는 1~1024자여야 합니다.")
    return result


def _name_filter(name: str) -> str:
    # A scalar eq value is literal text; request() URL-encodes the whole value.
    # Extra quotes would become part of the name PostgREST compares.
    return "eq." + name


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    try:
        return {
            "id": row["id"],
            "name": row["team_name"],
            "team_name": row["team_name"],
            "file_name": row["file_name"],
            "file_size": row["file_size"],
            "created_at": row["created_at"],
            "result": row["result"],
        }
    except (KeyError, TypeError):
        raise WCAAPIError("제출 데이터 형식이 올바르지 않습니다. result 컬럼을 포함한 DB 설정을 확인해주세요.") from None


class _Transport:
    def __init__(self, url: str, key: str, timeout: float):
        self.url = url
        self.key = key
        self.timeout = timeout
        context = ssl.create_default_context()
        context.load_verify_locations(cafile=certifi.where())
        self.opener = build_opener(_NoRedirect(), HTTPSHandler(context=context))

    def request(self, method: str, path: str, *, params=None, body=None, binary=False):
        url = self.url + path
        if params:
            url += "?" + urlencode(params)
        headers = {"apikey": self.key, "User-Agent": "WCA/0.2.2", "Accept": "application/octet-stream" if binary else "application/json"}
        if not self.key.startswith("sb_secret_"):
            headers["Authorization"] = "Bearer " + self.key
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
            headers.update({"Content-Type": "application/json", "Prefer": "return=representation"})
        request = Request(url, data=data, headers=headers, method=method)
        limit = _MAX_FILE_SIZE if binary else 8 * 1024 * 1024
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(limit + 1)
        except HTTPError as error:
            try:
                details = json.loads(error.read(16384))
            except (ValueError, OSError):
                details = {}
            if not isinstance(details, dict):
                details = {}
            message = str(details.get("message") or details.get("error") or "Supabase 요청에 실패했습니다.")
            message = message.replace(self.key, "[redacted]")[:500]
            raise WCAAPIError(message, status=error.code, code=details.get("code")) from None
        except (URLError, TimeoutError, OSError) as error:
            reason = error.reason if isinstance(error, URLError) else error
            if isinstance(reason, ssl.SSLCertVerificationError):
                raise WCAAPIError("HTTPS 인증서를 확인할 수 없습니다. WCA와 certifi를 업데이트하고 인증서 설정을 확인해주세요.", code="TLS_CERTIFICATE_ERROR") from None
            if isinstance(reason, socket.gaierror):
                raise WCAAPIError("Supabase 주소를 찾을 수 없습니다. 프로젝트 주소와 인터넷 연결을 확인해주세요.", code="DNS_ERROR") from None
            if isinstance(reason, TimeoutError):
                raise WCAAPIError("Supabase 연결 시간이 초과됐습니다. 인터넷 연결 또는 timeout 설정을 확인해주세요.", code="TIMEOUT") from None
            raise WCAAPIError("Supabase에 연결할 수 없습니다. 인터넷 연결과 프록시 설정을 확인해주세요.", code="CONNECTION_ERROR") from None
        if len(raw) > limit:
            raise WCAAPIError("서버 응답이 허용된 크기를 초과했습니다.")
        if binary:
            return raw
        try:
            return json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise WCAAPIError("Supabase가 올바른 JSON 응답을 반환하지 않았습니다.") from None


class WCA:
    """An independent client; credentials are read from the environment by default."""

    def __init__(self, url: str | None = None, secret_key: str | None = None, *, download_dir: str | Path | None = None, timeout: float = 30):
        url = url or os.environ.get("WCA_SUPABASE_URL") or os.environ.get("SUPABASE_URL") or DEFAULT_URL
        parsed = urlsplit(url.strip())
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise WCAConfigError("Supabase 프로젝트의 HTTPS 주소를 입력해주세요.")
        if not parsed.hostname.endswith(".supabase.co"):
            raise WCAConfigError("관리자 키는 Supabase 프로젝트의 .supabase.co 주소에만 전송합니다.")
        if secret_key is None:
            secret_key = os.environ.get("WCA_SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        key = _validated_key(secret_key)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout은 양수여야 합니다.")
        self.download_dir = Path(download_dir if download_dir is not None else os.environ.get("WCA_DOWNLOAD_DIR", "downloads")).expanduser()
        self._transport = _Transport(url.strip().rstrip("/"), key, timeout)

    def _set_secret_key(self, secret_key: str) -> None:
        self._transport.key = _validated_key(secret_key)

    def _rows(self, **params) -> list[dict[str, Any]]:
        rows = self._transport.request("GET", "/rest/v1/team_submissions", params=params)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise WCAAPIError("제출 목록 응답이 올바르지 않습니다.")
        return rows

    def list(self) -> list[dict[str, Any]]:
        """Return all submissions, oldest first, including their result."""
        result = []
        offset = 0
        while True:
            rows = self._rows(select=_FIELDS, order="created_at.asc,id.asc", limit=_PAGE_SIZE, offset=offset)
            result.extend(_metadata(row) for row in rows)
            if not rows:
                return result
            offset += len(rows)

    def frist(self, download_dir: str | Path | None = None) -> dict[str, Any] | None:
        """Download the oldest result=X Python file; return metadata and a local Path."""
        rows = self._rows(select=_FIELDS + ",storage_bucket,storage_path", result="eq.X", order="created_at.asc,id.asc", limit=1)
        if not rows:
            return None
        row = rows[0]
        metadata = _metadata(row)
        identifier = _submission_id(metadata["id"])
        try:
            bucket, path = row["storage_bucket"], row["storage_path"]
            size = row["file_size"]
            if bucket != "team-python-files" or not isinstance(path, str) or not path.endswith("/" + identifier + ".py") or not str(row["file_name"]).lower().endswith(".py") or isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= _MAX_FILE_SIZE:
                raise ValueError
        except (KeyError, ValueError, TypeError):
            raise WCAAPIError("제출 파일 정보가 올바르지 않습니다.") from None
        content = self._transport.request("GET", "/storage/v1/object/authenticated/" + quote(bucket, safe="") + "/" + quote(path, safe="/"), binary=True)
        if len(content) != size:
            raise WCAAPIError("다운로드한 파일 크기가 제출 정보와 다릅니다. 다시 시도해주세요.")
        directory = Path(download_dir).expanduser() if download_dir is not None else self.download_dir
        directory.mkdir(parents=True, exist_ok=True)
        target = directory.resolve() / (identifier + ".py")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, prefix=".wca-", delete=False) as output:
                temporary = Path(output.name)
                output.write(content)
            temporary.replace(target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return {**metadata, "path": target}

    def first(self, secret_key: str | None = None, *, download_dir: str | Path | None = None) -> dict[str, Any] | None:
        """Download the oldest pending file, optionally changing the admin key."""
        if secret_key is not None:
            self._set_secret_key(secret_key)
        return self.frist(download_dir)

    def spend(self, name: str, value: str | int | float, *, submission_id: str | None = None) -> dict[str, Any]:
        """Set the result of one matching pending submission, without overwriting a result."""
        name, value = _name(name), _result(value)
        params = {"select": _FIELDS, "team_name": _name_filter(name), "result": "eq.X", "order": "created_at.asc,id.asc", "limit": 1}
        if submission_id is not None:
            params["id"] = "eq." + _submission_id(submission_id)
        rows = self._rows(**params)
        if not rows:
            raise WCANotFoundError("해당 이름과 제출 ID에 결과가 X인 제출이 없습니다.")
        identifier = _submission_id(rows[0]["id"])
        saved = self._transport.request("PATCH", "/rest/v1/team_submissions", params={"id": "eq." + identifier, "team_name": _name_filter(name), "result": "eq.X", "select": _FIELDS}, body={"result": value})
        if not isinstance(saved, list):
            raise WCAAPIError("결과 갱신 응답이 올바르지 않습니다.")
        if not saved:
            raise WCAConflictError("이미 처리되었거나 변경된 제출입니다. 결과를 덮어쓰지 않았습니다.")
        if len(saved) != 1:
            raise WCAAPIError("결과 갱신 응답의 제출 수가 올바르지 않습니다.")
        return _metadata(saved[0])
