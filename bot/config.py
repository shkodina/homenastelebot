from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import yaml

from bot.disks import DEFAULT_MIN_BYTES


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class ProxyConfig:
    enabled: bool
    type: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None


@dataclass(frozen=True)
class FtpConfig:
    service: str = "vsftpd"
    flag: str = "/xtmp-docker/ftp"
    result: str = "/xtmp-docker/ftp.result"
    user: str = ""
    password: str = ""
    endpoint_internal: str = ""
    endpoint_external: str = ""
    send_login_data: bool = False
    send_server_info: bool = False
    send_in_split_messages: bool = False


@dataclass(frozen=True)
class Config:
    token: str
    allowed_ids: frozenset[int]
    uptime_path: str = "/proc/uptime"
    host_root: str = "/host"
    df_min_bytes: int = DEFAULT_MIN_BYTES
    docker_socket: str = "/var/run/docker.sock"
    restart_flag: str = "/xtmp-docker/restart"
    restart_skip: tuple[str, ...] = ("homenasbot",)
    proxy: ProxyConfig | None = None
    cursor_api_key: str = ""
    ftp: FtpConfig = FtpConfig()


def proxy_url(config: Config) -> str | None:
    proxy = config.proxy
    if proxy is None or not proxy.enabled:
        return None

    scheme = "socks5" if proxy.type in ("socks5", "socks5h") else proxy.type
    auth = ""
    if proxy.username:
        user = quote(proxy.username, safe="")
        password = quote(proxy.password or "", safe="")
        auth = f"{user}:{password}@"
    return f"{scheme}://{auth}{proxy.host}:{proxy.port}"


def proxy_log_target(config: Config) -> str | None:
    proxy = config.proxy
    if proxy is None or not proxy.enabled:
        return None
    return f"{proxy.type}://{proxy.host}:{proxy.port}"


def _parse_proxy(raw: object) -> ProxyConfig | None:
    if not raw:
        return None
    if not isinstance(raw, dict):
        raise ConfigError("telegram.proxy must be a mapping")

    enabled = bool(raw.get("enabled", False))
    if not enabled:
        return None

    proxy_type = str(raw.get("type") or "socks5").strip().lower()
    host = str(raw.get("host") or "").strip()
    if not host:
        raise ConfigError("telegram.proxy.host is required when proxy is enabled")

    try:
        port = int(raw.get("port"))
    except (TypeError, ValueError) as exc:
        raise ConfigError("telegram.proxy.port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ConfigError("telegram.proxy.port must be in 1..65535")

    username = str(raw.get("username") or "").strip() or None
    password = str(raw.get("password") or "") or None
    if username is None:
        password = None

    return ProxyConfig(
        enabled=True,
        type=proxy_type,
        host=host,
        port=port,
        username=username,
        password=password,
    )


def _as_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_map(raw: object, name: str) -> dict:
    if not raw:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{name} must be a mapping")
    return raw


def _parse_ftp(data: dict) -> FtpConfig:
    ftp = _as_map(data.get("ftp"), "ftp")
    vsftpd = _as_map(data.get("vsftpd"), "vsftpd")
    send = vsftpd.get("send_on_start") or ftp.get("send_on_start") or {}
    send = _as_map(send, "vsftpd.send_on_start")
    endpoints = vsftpd.get("endpoints") or ftp.get("endpoints") or {}
    endpoints = _as_map(endpoints, "vsftpd.endpoints")
    split = send.get("send_in_splited_messages")
    if split is None:
        split = send.get("send_in_split_messages")
    return FtpConfig(
        service=str(ftp.get("service") or vsftpd.get("service") or "vsftpd").strip() or "vsftpd",
        flag=str(ftp.get("flag") or vsftpd.get("flag") or "/xtmp-docker/ftp").strip()
        or "/xtmp-docker/ftp",
        result=str(ftp.get("result") or vsftpd.get("result") or "/xtmp-docker/ftp.result").strip()
        or "/xtmp-docker/ftp.result",
        user=str(vsftpd.get("user") or ftp.get("user") or "").strip(),
        password=str(vsftpd.get("pass") or vsftpd.get("password") or ftp.get("pass") or "").strip(),
        endpoint_internal=str(endpoints.get("internal") or "").strip(),
        endpoint_external=str(endpoints.get("external") or "").strip(),
        send_login_data=_as_bool(send.get("send_login_data")),
        send_server_info=_as_bool(send.get("send_server_info")),
        send_in_split_messages=_as_bool(split),
    )


def load_config(path: str) -> Config:
    config_path = Path(path)
    if not config_path.is_file():
        raise ConfigError(f"config not found: {config_path}")

    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid yaml: {exc}") from exc

    telegram = data.get("telegram") or {}
    token = str(telegram.get("token") or "").strip()
    if not token:
        raise ConfigError("telegram.token is required")

    raw_ids = telegram.get("allowed_ids") or []
    try:
        allowed_ids = frozenset(int(item) for item in raw_ids)
    except (TypeError, ValueError) as exc:
        raise ConfigError("telegram.allowed_ids must be a list of integers") from exc
    if not allowed_ids:
        raise ConfigError("telegram.allowed_ids must not be empty")

    nas = data.get("nas") or {}
    uptime_path = str(nas.get("uptime_path") or "/proc/uptime")
    host_root = str(nas.get("host_root") or "/host")
    try:
        df_min_bytes = int(nas.get("df_min_bytes") or DEFAULT_MIN_BYTES)
    except (TypeError, ValueError) as exc:
        raise ConfigError("nas.df_min_bytes must be an integer") from exc

    docker = data.get("docker") or {}
    docker_socket = str(docker.get("socket") or "/var/run/docker.sock")
    restart_flag = str(docker.get("restart_flag") or "/xtmp-docker/restart")
    raw_skip = docker.get("restart_skip")
    if raw_skip is None:
        restart_skip = ("homenasbot",)
    else:
        restart_skip = tuple(str(item) for item in raw_skip if str(item).strip())

    proxy = _parse_proxy(telegram.get("proxy"))

    cursor = data.get("cursor") or {}
    if cursor and not isinstance(cursor, dict):
        raise ConfigError("cursor must be a mapping")
    cursor_api_key = str((cursor or {}).get("api_key") or "").strip()
    ftp = _parse_ftp(data)

    return Config(
        token=token,
        allowed_ids=allowed_ids,
        uptime_path=uptime_path,
        host_root=host_root,
        df_min_bytes=df_min_bytes,
        docker_socket=docker_socket,
        restart_flag=restart_flag,
        restart_skip=restart_skip,
        proxy=proxy,
        cursor_api_key=cursor_api_key,
        ftp=ftp,
    )
