import os
import sys
import tempfile
from pathlib import Path

from attrs import define
from platformdirs import PlatformDirs

APP_NAME = "kiosk-agent"


@define(frozen=True, slots=True)
class AgentPaths:
    data: Path
    config: Path
    cache: Path
    runtime: Path
    profile: Path


def get_paths() -> AgentPaths:
    dirs = PlatformDirs(APP_NAME, appauthor=False)
    return AgentPaths(
        dirs.user_data_path,
        dirs.user_config_path,
        dirs.user_cache_path,
        dirs.user_runtime_path,
        dirs.user_data_path / "chromium",
    )


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve()


def _is_relative_to(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def ephemeral_runtime_reason(executable: Path | None = None) -> str | None:
    raw_executable = (
        (executable or Path(sys.executable)).expanduser().absolute()
    )
    executable = _resolved(raw_executable)
    candidates = (raw_executable, executable)
    temp_root = _resolved(Path(tempfile.gettempdir()))
    uv_cache = os.environ.get("UV_CACHE_DIR")
    uv_cache_root = _resolved(
        Path(uv_cache)
        if uv_cache
        else PlatformDirs("uv", appauthor=False).user_cache_path
    )

    if any(_is_relative_to(path, temp_root) for path in candidates):
        return f"interpreter is inside temporary directory {temp_root}"
    if any(_is_relative_to(path, uv_cache_root) for path in candidates):
        return f"interpreter is inside uv cache directory {uv_cache_root}"
    if any("archive-v0" in path.parts for path in candidates):
        return "interpreter is inside a uv archive environment"
    return None


def ensure_profile_dir(profile_dir: Path | None = None) -> Path:
    path = _resolved(profile_dir or get_paths().profile)
    path.mkdir(parents=True, exist_ok=True)
    return path
