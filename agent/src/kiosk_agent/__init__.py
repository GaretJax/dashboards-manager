from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("kiosk-agent")
except PackageNotFoundError:
    __version__ = "0.1.1"
