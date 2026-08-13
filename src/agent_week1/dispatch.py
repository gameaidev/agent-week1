import ipaddress
import os
import socket
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit


_DEFAULT_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = Path(
    os.getenv("AGENT_WORKSPACE_ROOT", str(_DEFAULT_WORKSPACE_ROOT))
).expanduser().resolve()

MAX_FILE_BYTES = 1_000_000
MAX_HTTP_BYTES = 2_000_000
MAX_SCRIPT_OUTPUT_BYTES = 100_000
HTTP_TIMEOUT_SECONDS = 10
SCRIPT_TIMEOUT_SECONDS = 30


def _resolve_workspace_file(filepath: str) -> Path:
    candidate = Path(filepath).expanduser()
    if not candidate.is_absolute():
        candidate = WORKSPACE_ROOT / candidate

    path = candidate.resolve(strict=True)
    try:
        path.relative_to(WORKSPACE_ROOT)
    except ValueError as exc:
        raise PermissionError(
            f"Path must be inside the workspace: {WORKSPACE_ROOT}"
        ) from exc

    if not path.is_file():
        raise ValueError(f"Path is not a regular file: {path}")
    return path


def _read_limited(path: Path, limit: int) -> bytes:
    with path.open("rb") as file:
        data = file.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"File exceeds the {limit:,}-byte limit: {path}")
    return data


def read_file(filepath: str) -> str:
    path = _resolve_workspace_file(filepath)
    return _read_limited(path, MAX_FILE_BYTES).decode("utf-8")


def _safe_subprocess_environment() -> dict[str, str]:
    sensitive_markers = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
    return {
        name: value
        for name, value in os.environ.items()
        if not any(marker in name.upper() for marker in sensitive_markers)
    }


def _truncate_output(output: str) -> str:
    encoded = output.encode("utf-8")
    if len(encoded) <= MAX_SCRIPT_OUTPUT_BYTES:
        return output
    truncated = encoded[:MAX_SCRIPT_OUTPUT_BYTES].decode("utf-8", errors="ignore")
    return f"{truncated}\n[output truncated]"


def run_bash(filepath: str, *, approved: bool = False) -> str:
    if not approved:
        raise PermissionError("Bash execution requires explicit user approval.")

    path = _resolve_workspace_file(filepath)
    try:
        status = subprocess.run(
            ["bash", "--", str(path)],
            cwd=WORKSPACE_ROOT,
            env=_safe_subprocess_environment(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=SCRIPT_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"Script exceeded the {SCRIPT_TIMEOUT_SECONDS}-second limit."
        ) from exc

    output = status.stdout
    if status.stderr:
        output += f"\nstderr:\n{status.stderr}"
    output = _truncate_output(output.strip())

    if status.returncode != 0:
        detail = output or "No output was produced."
        raise RuntimeError(f"Script exited with status {status.returncode}:\n{detail}")
    return output or "Script completed successfully with no output."


def _validate_public_https_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https":
        raise ValueError("Only HTTPS URLs are allowed.")
    if not parsed.hostname:
        raise ValueError("URL must include a hostname.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URLs containing credentials are not allowed.")

    try:
        port = parsed.port or 443
    except ValueError as exc:
        raise ValueError("URL contains an invalid port.") from exc

    try:
        addresses = socket.getaddrinfo(
            parsed.hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve hostname: {parsed.hostname}") from exc

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0].split("%", maxsplit=1)[0])
        if not ip.is_global:
            raise PermissionError(
                f"URL resolves to a non-public address: {ip}"
            )
    return url


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        _validate_public_https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def http_get(url: str) -> str:
    _validate_public_https_url(url)
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/*, application/json, application/xml",
            "User-Agent": "agent-week1/0.1",
        },
    )
    opener = urllib.request.build_opener(_SafeRedirectHandler())

    with opener.open(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        _validate_public_https_url(response.geturl())
        content_type = response.headers.get_content_type().lower()
        allowed_application_types = {
            "application/json",
            "application/javascript",
            "application/xml",
            "application/xhtml+xml",
        }
        if (
            not content_type.startswith("text/")
            and content_type not in allowed_application_types
        ):
            raise ValueError(f"Unsupported response content type: {content_type}")

        content_length = response.headers.get("Content-Length")
        if content_length is not None and int(content_length) > MAX_HTTP_BYTES:
            raise ValueError(
                f"Response exceeds the {MAX_HTTP_BYTES:,}-byte limit."
            )

        body = response.read(MAX_HTTP_BYTES + 1)
        if len(body) > MAX_HTTP_BYTES:
            raise ValueError(
                f"Response exceeds the {MAX_HTTP_BYTES:,}-byte limit."
            )
        charset = response.headers.get_content_charset() or "utf-8"
        return body.decode(charset, errors="replace")


DISPATCH: dict[str, Callable[..., Any]] = {
    "read_file": read_file,
    "run_bash": run_bash,
    "http_get": http_get,
}
