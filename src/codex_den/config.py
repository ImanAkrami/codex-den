"""One typed schema and precedence model for files, flags and Settings."""

import copy
import tomllib
from pathlib import Path

import tomli_w

from .errors import DenError
from .storage import atomic_bytes, lock_file, protect_path

DEFAULTS = {
    "frontend": "vscode",
    "executables.vscode": "code",
    "executables.cursor": "cursor",
    "ui.color": "auto",
    "ui.theme": "dark",
    "ui.motion": True,
    "ui.plain": False,
    "ui.ascii": False,
    "discovery.max_depth": 3,
}
CHOICES = {
    "frontend": ("vscode", "cursor"),
    "ui.color": ("auto", "never", "always"),
    "ui.theme": ("dark", "light"),
}


def validate(key: str, value):
    if key not in DEFAULTS:
        raise DenError(f"Unknown setting {key!r}. Use config show to list supported keys.")
    if type(value) is not type(DEFAULTS[key]):
        raise DenError(f"Invalid type for {key}; expected {type(DEFAULTS[key]).__name__}.")
    if key in CHOICES and value not in CHOICES[key]:
        raise DenError(f"Invalid {key}; choose {', '.join(CHOICES[key])}.")
    if key.startswith("executables.") and ("\x00" in value or not value.strip()):
        raise DenError(f"{key} must be a nonempty executable path or command.")
    if key == "discovery.max_depth" and not 1 <= value <= 20:
        raise DenError("discovery.max_depth must be between 1 and 20.")
    return value


def parse_overrides(items: list[str]) -> dict:
    result = {}
    for item in items:
        key, separator, raw = item.partition("=")
        if not separator:
            raise DenError("Settings use KEY=VALUE; see config show for supported keys.")
        if key not in DEFAULTS:
            validate(key, raw)
        if isinstance(DEFAULTS[key], str):
            value = raw
        else:
            try:
                value = tomllib.loads(f"value = {raw}")["value"]
            except (tomllib.TOMLDecodeError, KeyError):
                raise DenError(f"Invalid typed value for {key}.") from None
        validate(key, value)
        if key in result and result[key] != value:
            raise DenError(f"Conflicting arguments for {key}.")
        result[key] = value
    return result


def flatten(value: dict, prefix="") -> dict:
    result = {}
    for key, item in value.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            result.update(flatten(item, name))
        else:
            result[name] = item
    return result


def nested(values: dict) -> dict:
    result = {"schema_version": 1}
    for key, value in values.items():
        target = result
        parts = key.split(".")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value
    return result


class Configuration:
    def __init__(self, path: Path, overrides: dict | None = None, explicit=False):
        self.path = protect_path(path)
        self.overrides = overrides or {}
        self.explicit = explicit
        for key, value in self.overrides.items():
            validate(key, value)

    def saved(self) -> dict:
        if not self.path.exists():
            if self.explicit:
                raise DenError(f"Configuration does not exist: {self.path}")
            return {}
        try:
            data = tomllib.loads(self.path.read_text())
        except (tomllib.TOMLDecodeError, OSError) as error:
            raise DenError(
                f"Cannot read configuration {self.path}; fix it or restore a backup."
            ) from error
        if data.pop("schema_version", 1) != 1:
            raise DenError("Unsupported configuration schema; use a compatible Codex Den version.")
        values = flatten(data)
        for key, value in values.items():
            validate(key, value)
        return values

    def resolve(self, environment=None, workspace=None):
        values, sources = copy.deepcopy(DEFAULTS), dict.fromkeys(DEFAULTS, "default")
        for source, layer in (
            ("user", self.saved()),
            ("environment", environment or {}),
            ("workspace", workspace or {}),
            ("argument", self.overrides),
        ):
            for key, value in layer.items():
                values[key] = validate(key, value)
                sources[key] = source
        return values, sources

    def effective(self, environment=None, workspace=None):
        return self.resolve(environment, workspace)[0]

    def sources(self, environment=None, workspace=None):
        return self.resolve(environment, workspace)[1]

    def save(self, key: str, value):
        validate(key, value)
        with lock_file(self.path.with_suffix(".lock")):
            values = self.saved()
            values[key] = value
            atomic_bytes(self.path, tomli_w.dumps(nested(values)).encode())

    def reset(self, key: str):
        if key not in DEFAULTS:
            raise DenError("Unknown setting; reset requires an exact supported key.")
        with lock_file(self.path.with_suffix(".lock")):
            values = self.saved()
            values.pop(key, None)
            atomic_bytes(self.path, tomli_w.dumps(nested(values)).encode())
