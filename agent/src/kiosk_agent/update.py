import shutil
import subprocess
import sys
from email.parser import Parser
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from attrs import define
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.tags import sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import InvalidVersion, Version

MAX_WHEEL_SIZE = 20 * 1024 * 1024
PACKAGE_NAME = "kiosk-agent"


class UpdateError(RuntimeError):
    """An agent update could not be validated or installed."""


@define(frozen=True, slots=True)
class AgentUpdate:
    filename: str
    url: str
    version: str


def parse_wheel_location(
    stable_url: str,
    location: str,
) -> AgentUpdate:
    from urllib.parse import urljoin, urlsplit

    candidate = urljoin(stable_url, location)
    stable = urlsplit(stable_url)
    target = urlsplit(candidate)
    stable_prefix = stable.path.rsplit("/downloads/", 1)[0]
    if (
        target.scheme != stable.scheme
        or target.netloc != stable.netloc
        or target.query
        or target.fragment
        or not target.path.startswith(f"{stable_prefix}/downloads/")
    ):
        raise UpdateError("manager returned an unsafe wheel redirect")
    filename = Path(target.path).name
    try:
        name, version, _build, _tags = parse_wheel_filename(filename)
    except (TypeError, ValueError) as exc:
        raise UpdateError(
            "manager returned an invalid wheel filename"
        ) from exc
    if canonicalize_name(str(name)) != canonicalize_name(PACKAGE_NAME):
        raise UpdateError("manager returned a wheel for another package")
    return AgentUpdate(filename, candidate, str(version))


def verify_wheel(path: Path, expected: AgentUpdate):
    if path.stat().st_size > MAX_WHEEL_SIZE:
        raise UpdateError("agent wheel exceeds maximum size")
    try:
        name, version, _build, tags = parse_wheel_filename(path.name)
        with ZipFile(path) as wheel:
            metadata_name = next(
                name
                for name in wheel.namelist()
                if name.endswith(".dist-info/METADATA")
            )
            metadata = Parser().parsestr(
                wheel.read(metadata_name).decode("utf-8")
            )
    except (BadZipFile, UnicodeDecodeError, StopIteration, ValueError) as exc:
        raise UpdateError("downloaded file is not a valid wheel") from exc
    if canonicalize_name(str(name)) != canonicalize_name(PACKAGE_NAME):
        raise UpdateError("downloaded wheel has an unexpected package name")
    if str(version) != expected.version:
        raise UpdateError("downloaded wheel version does not match redirect")
    if canonicalize_name(metadata.get("Name", "")) != canonicalize_name(
        PACKAGE_NAME
    ):
        raise UpdateError("wheel metadata has an unexpected package name")
    if metadata.get("Version") != expected.version:
        raise UpdateError("wheel metadata version does not match redirect")
    requires_python = metadata.get("Requires-Python")
    try:
        supported_python = not requires_python or Version(
            f"{sys.version_info.major}.{sys.version_info.minor}"
        ) in SpecifierSet(requires_python or "")
    except (InvalidSpecifier, InvalidVersion) as exc:
        raise UpdateError("wheel has invalid Python requirements") from exc
    if not supported_python:
        raise UpdateError("agent wheel requires an unsupported Python version")
    if not tags or not tags.intersection(sys_tags()):
        raise UpdateError("wheel has no compatible tags")


def _tool_executable(name: str) -> str | None:
    executable = shutil.which(name)
    if executable:
        return executable
    candidate = Path.home() / ".local" / "bin" / name
    return str(candidate) if candidate.is_file() else None


def install_wheel(path: Path, expected: AgentUpdate):
    uv = _tool_executable("uv")
    if uv is None:
        raise UpdateError("persistent uv executable not found")
    result = subprocess.run(  # noqa: S603
        [uv, "tool", "install", "--force", str(path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "uv failed").strip()
        raise UpdateError(f"uv installation failed: {detail[:300]}")
    executable = _tool_executable("kiosk-agent")
    command = (
        [executable, "--version"]
        if executable is not None
        else [sys.executable, "-m", "kiosk_agent", "--version"]
    )
    result = subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0 or expected.version not in result.stdout:
        raise UpdateError(
            "installed kiosk-agent version could not be verified"
        )


def refresh_service(config_name: str | Path):
    executable = _tool_executable("kiosk-agent")
    command = (
        [executable, "service", "install"]
        if executable is not None
        else [sys.executable, "-m", "kiosk_agent", "service", "install"]
    )
    command.extend(["--config", str(config_name), "--no-start"])
    result = subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if result.returncode != 0:
        detail = (
            result.stderr or result.stdout or "service refresh failed"
        ).strip()
        raise UpdateError(f"systemd unit refresh failed: {detail[:300]}")


def compare_versions(current: str, remote: str) -> int:
    try:
        current_version = Version(current)
        remote_version = Version(remote)
    except InvalidVersion as exc:
        raise UpdateError("invalid agent version") from exc
    return (remote_version > current_version) - (
        remote_version < current_version
    )
