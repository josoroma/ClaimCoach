"""The typed ``models.yaml`` registry: per role, a model dir, venv, command, and port.

Implements: US-2.1 (``ModelSpec``, ``ModelRegistry``, default file written on first run), US-2.3
(the size-tier table: ``tier_b``, ``runs_alone``, ``ResidencyPolicy``), US-2.4 (``repo_id``,
``ConversionSpec``, ``AcquireCommands``, weights presence), US-7.1 (an unedited pre-US-7.1 copy's
``drafting`` command gains ``--reasoning off``, once), US-11.1 (the ``{logs}`` placeholder; an
unedited pre-US-11.1 copy's ``transcription`` command drops the ``--model`` flag
``mlx_audio.server`` does not have and gains ``--log-dir {logs}``, once). Rules: BR-11 (weights
read in place under ``MODELS_HOME``, never copied; ports 18200-18219), BR-12, ES-1.

Paths are validated lexically and never resolved: a model symlinked into ``MODELS_HOME`` stays
usable, and nothing here touches a weight file.
"""

from __future__ import annotations

import json
import os
import string
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Annotated, Final, Literal

import yaml
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic import model_validator as _model_validator

from claimcoach.models.types import ModelRole, WeightsState
from claimcoach.settings import PORT_RANGE

__all__ = [
    "DEFAULT_REGISTRY",
    "REGISTRY_FILE",
    "SERVER_PLACEHOLDERS",
    "WORKER_PORT",
    "AcquireCommands",
    "ConversionSpec",
    "ModelRegistry",
    "ModelSpec",
    "RegistryError",
    "ResidencyPolicy",
    "ensure_registry_file",
    "load_registry",
    "models_home",
]

REGISTRY_FILE: Final = "models.yaml"
DEFAULT_REGISTRY: Final = Path(__file__).with_name("models.default.yaml")
"""The packaged default, copied to the data dir on first run."""

WORKER_PORT: Final = PORT_RANGE.start
"""18200 belongs to the worker; model servers use the rest of the range."""

SERVER_PLACEHOLDERS: Final = frozenset({"venv", "model", "host", "port", "logs"})
_DOWNLOAD_PLACEHOLDERS: Final = frozenset({"models_home", "repo_id", "target"})
_CONVERT_PLACEHOLDERS: Final = frozenset({"models_home", "source", "target", "q_bits"})
_RANGE_TEXT: Final = f"{PORT_RANGE.start}-{PORT_RANGE.stop - 1}"


class RegistryError(ValueError):
    """``models.yaml`` is unreadable or invalid; the message names each bad entry."""


def models_home() -> Path:
    """Return ``MODELS_HOME`` (default ``~/Models``), user-expanded but not resolved."""
    return Path(os.environ.get("MODELS_HOME") or "~/Models").expanduser()


def _relative_dir(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or value.startswith("~") or ".." in path.parts or not path.parts:
        raise ValueError("must be a relative path inside MODELS_HOME without '..'")
    return value


def _placeholders(parts: Iterable[str]) -> set[str]:
    return {name for part in parts for _, name, _, _ in string.Formatter().parse(part) if name}


def _check_template(parts: list[str], allowed: frozenset[str], required: set[str]) -> list[str]:
    found = _placeholders(parts)
    if unknown := found - allowed:
        raise ValueError(f"unknown placeholder(s) {sorted(unknown)}; allowed: {sorted(allowed)}")
    if missing := required - found:
        raise ValueError(f"must contain the placeholder(s) {sorted(missing)}")
    return parts


RelativeDir = Annotated[str, AfterValidator(_relative_dir)]
RepoId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][\w.-]*/[\w.-]+$")]
VenvName = Annotated[str, Field(pattern=r"^[A-Za-z0-9][\w.-]*$")]
Argv = Annotated[list[Annotated[str, Field(min_length=1)]], Field(min_length=1)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _weights(path: Path) -> WeightsState:
    """Return whether ``path`` holds a complete model.

    It needs ``config.json`` and its weights: every shard named in
    ``model.safetensors.index.json`` when there is an index, otherwise at least one
    ``*.safetensors`` file. ``hf download`` moves each file into place only once it is complete,
    so an interrupted multi-shard download stays ``missing`` and is offered again (it resumes).
    """
    if not (path / "config.json").is_file():
        return "missing"
    index = path / "model.safetensors.index.json"
    if not index.exists():
        return "present" if next(path.glob("*.safetensors"), None) is not None else "missing"
    try:
        shards = set(json.loads(index.read_text(encoding="utf-8"))["weight_map"].values())
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return "missing"
    if shards and all((path / str(shard)).is_file() for shard in shards):
        return "present"
    return "missing"


class ConversionSpec(_Strict):
    """A role whose model is converted locally instead of downloaded ready-made (the reranker).

    Attributes:
        source_repo_id: Hugging Face repository of the source model.
        source_dir: Where the source is downloaded, relative to ``MODELS_HOME``.
        q_bits: Quantization bits of the converted model.
    """

    source_repo_id: RepoId
    source_dir: RelativeDir
    q_bits: int = Field(default=4, ge=2, le=8)


class ModelSpec(_Strict):
    """How to run the server for one role.

    Attributes:
        repo_id: Hugging Face repository downloaded into ``model_dir``; ``None`` when converted.
        convert: Local conversion recipe; ``None`` when downloaded ready-made.
        model_dir: Model directory, relative to ``MODELS_HOME``.
        venv: Venv name under ``MODELS_HOME/.venvs``.
        command: Server argv; placeholders ``{venv} {model} {host} {port} {logs}``.
        port: Loopback port inside 18201-18219.
        tier_b: Size tier in billions of parameters (memory guard, BR-12).
        runs_alone: Start only when no other ClaimCoach server is resident (Voxtral).
        startup_timeout_s: Seconds to wait for ``/v1/models`` after starting.
    """

    repo_id: RepoId | None = None
    convert: ConversionSpec | None = None
    model_dir: RelativeDir
    venv: VenvName
    command: Argv
    port: int
    tier_b: int = Field(gt=0)
    runs_alone: bool = False
    startup_timeout_s: float = Field(default=300.0, gt=0)

    @field_validator("port")
    @classmethod
    def _port_in_range(cls, port: int) -> int:
        if port not in PORT_RANGE:
            raise ValueError(f"port {port} is outside the allowed range {_RANGE_TEXT}")
        if port == WORKER_PORT:
            raise ValueError(f"port {port} is reserved for the ClaimCoach worker")
        return port

    @field_validator("command")
    @classmethod
    def _command_binds_loopback(cls, command: list[str]) -> list[str]:
        # A server that is not told {host} may bind its default, e.g. 0.0.0.0 for mlx_vlm.server.
        return _check_template(command, SERVER_PLACEHOLDERS, {"host", "port"})

    @_model_validator(mode="after")
    def _one_source(self) -> ModelSpec:
        if (self.repo_id is None) == (self.convert is None):
            raise ValueError("set exactly one of repo_id or convert")
        return self

    @property
    def server_identity(self) -> tuple[str, str, tuple[str, ...]]:
        """What two roles must agree on to share a port: model dir, venv, and command."""
        return (self.model_dir, self.venv, tuple(self.command))

    def model_path(self, home: Path) -> Path:
        """Return the model directory under ``home``."""
        return home / self.model_dir

    def venv_path(self, home: Path) -> Path:
        """Return the venv directory under ``home/.venvs``."""
        return home / ".venvs" / self.venv

    def argv(self, home: Path, host: str, logs: Path | None = None) -> list[str]:
        """Return the server argv with every placeholder filled in.

        Args:
            home: ``MODELS_HOME``.
            host: The loopback host.
            logs: The folder ``{logs}`` names (the manager's, in the data dir); ``home/.logs``
                when not given, for display only.
        """
        values = {
            "venv": str(self.venv_path(home)),
            "model": str(self.model_path(home)),
            "host": host,
            "port": str(self.port),
            "logs": str(logs or home / ".logs"),
        }
        return [part.format_map(values) for part in self.command]

    def weights(self, home: Path) -> WeightsState:
        """Return whether ``model_dir`` holds a model."""
        return _weights(self.model_path(home))

    def source_present(self, home: Path) -> bool | None:
        """For converted roles, whether the source model is present; ``None`` otherwise."""
        if self.convert is None:
            return None
        return _weights(home / self.convert.source_dir) == "present"

    def venv_present(self, home: Path) -> bool:
        """Return whether the venv has an interpreter."""
        return (self.venv_path(home) / "bin" / "python").exists()


class ResidencyPolicy(_Strict):
    """Memory-guard thresholds (BR-12).

    Attributes:
        large_tier_b: Servers at or above this tier count as large; at most one is resident.
    """

    large_tier_b: int = Field(default=14, gt=0)


class AcquireCommands(_Strict):
    """Command templates for confirmed downloads and local conversion (US-2.4).

    Attributes:
        download: Placeholders ``{models_home} {repo_id} {target}``.
        convert: Placeholders ``{models_home} {source} {target} {q_bits}``.
    """

    download: Argv
    convert: Argv

    @field_validator("download")
    @classmethod
    def _download_template(cls, argv: list[str]) -> list[str]:
        return _check_template(argv, _DOWNLOAD_PLACEHOLDERS, {"repo_id", "target"})

    @field_validator("convert")
    @classmethod
    def _convert_template(cls, argv: list[str]) -> list[str]:
        return _check_template(argv, _CONVERT_PLACEHOLDERS, {"source", "target"})


class ModelRegistry(_Strict):
    """The whole ``models.yaml``.

    Attributes:
        version: File format version.
        idle_timeout_s: Seconds a server may sit unused before the idle sweep stops it.
        queue_timeout_s: Longest a load may wait on the memory guard.
        residency: Memory-guard thresholds.
        acquire: Download and conversion command templates.
        roles: One spec per ``ModelRole``.
    """

    version: Literal[1] = 1
    idle_timeout_s: float = Field(default=600.0, gt=0)
    queue_timeout_s: float = Field(default=900.0, gt=0)
    residency: ResidencyPolicy = ResidencyPolicy()
    acquire: AcquireCommands
    roles: dict[ModelRole, ModelSpec]

    @field_validator("roles")
    @classmethod
    def _complete_and_consistent(
        cls, roles: dict[ModelRole, ModelSpec]
    ) -> dict[ModelRole, ModelSpec]:
        if missing := [role.value for role in ModelRole if role not in roles]:
            raise ValueError(f"missing roles: {', '.join(missing)}")
        for port, sharing in _group_by_port(roles).items():
            identities = {roles[role].server_identity for role in sharing}
            if len(identities) > 1:
                names = ", ".join(role.value for role in sharing)
                raise ValueError(f"roles {names} share port {port} but describe different servers")
        return roles

    def servers(self) -> dict[int, list[ModelRole]]:
        """Return the roles served by each port; roles on one port share one process."""
        return _group_by_port(self.roles)

    @classmethod
    def load(cls, path: Path) -> ModelRegistry:
        """Read and validate ``path``.

        Args:
            path: A ``models.yaml`` file.

        Returns:
            The registry.

        Raises:
            RegistryError: The file is unreadable, not YAML, or invalid; the message names each
                bad entry, e.g. ``roles.classification.port: port 18300 is outside ...``.
        """
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            raise RegistryError(f"{path.name}: cannot read the file") from exc
        except yaml.YAMLError as exc:
            raise RegistryError(f"{path.name}: not valid YAML") from exc
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise RegistryError(_describe(path.name, exc)) from exc


def _group_by_port(roles: Mapping[ModelRole, ModelSpec]) -> dict[int, list[ModelRole]]:
    groups: dict[int, list[ModelRole]] = {}
    for role, spec in roles.items():
        groups.setdefault(spec.port, []).append(role)
    return groups


def _describe(name: str, exc: ValidationError) -> str:
    lines = []
    for error in exc.errors(include_input=False, include_url=False):
        where = ".".join(str(part) for part in error["loc"]) or "<root>"
        message = error["msg"].removeprefix("Value error, ")
        lines.append(f"{name}: {where}: {message}")
    return "\n".join(lines)


_OLD_DRAFTING_COMMAND: Final = (
    '    command: ["{venv}/bin/mtplx", "serve", "--model", "{model}", "--host", "{host}", '
    '"--port", "{port}", "--no-auth"]\n'
)
"""The ``drafting`` command shipped before US-7.1, exactly as the default file spelled it."""
_DRAFTING_COMMAND: Final = (
    '    command: ["{venv}/bin/mtplx", "serve", "--model", "{model}", "--host", "{host}", '
    '"--port", "{port}", "--no-auth", "--reasoning", "off"]\n'
)


_OLD_TRANSCRIPTION_COMMAND: Final = (
    '    command: ["{venv}/bin/python", "-m", "mlx_audio.server", "--model", "{model}", '
    '"--host", "{host}", "--port", "{port}"]\n'
)
"""The ``transcription`` command shipped before US-11.1: ``mlx_audio.server`` has no ``--model``."""
_TRANSCRIPTION_COMMAND: Final = (
    '    command: ["{venv}/bin/python", "-m", "mlx_audio.server", "--host", "{host}", '
    '"--port", "{port}", "--log-dir", "{logs}"]\n'
)
_COMMAND_MIGRATIONS: Final = (
    (_OLD_DRAFTING_COMMAND, _DRAFTING_COMMAND),
    (_OLD_TRANSCRIPTION_COMMAND, _TRANSCRIPTION_COMMAND),
)


def _migrate_commands(path: Path) -> None:
    """Bring unedited old default commands up to date, once.

    The ``drafting`` command gains ``--reasoning off`` (US-7.1); the ``transcription`` command
    drops ``--model`` and gains ``--log-dir {logs}`` (US-11.1). Only the exact lines an old default
    shipped are replaced (written to a temporary file and renamed into place, keeping the file's
    mode); an edited command is left as the user wrote it (the upgrade runbook says how to change
    it by hand).
    """
    text = original = path.read_text()
    for old, new in _COMMAND_MIGRATIONS:
        if text.count(old) == 1:
            text = text.replace(old, new)
    if text == original:
        return
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text)
    tmp.chmod(path.stat().st_mode & 0o777)
    tmp.replace(path)


def ensure_registry_file(data_dir: Path) -> Path:
    """Write the default ``models.yaml`` into ``data_dir`` unless one is already there.

    The default is written to a temporary file and hard-linked into place, so a concurrent
    start never sees a partial file and an existing (possibly edited) file is never replaced;
    only unedited old default commands are migrated (``_migrate_commands``).

    Args:
        data_dir: The ClaimCoach data dir.

    Returns:
        Path of ``models.yaml``.
    """
    path = data_dir / REGISTRY_FILE
    if path.exists():
        _migrate_commands(path)
        return path
    data_dir.mkdir(parents=True, exist_ok=True)
    tmp = data_dir / f".{REGISTRY_FILE}.{os.getpid()}.tmp"
    tmp.write_bytes(DEFAULT_REGISTRY.read_bytes())
    try:
        os.link(tmp, path)
    except FileExistsError:
        pass  # another process wrote it first; keep theirs
    finally:
        tmp.unlink()
    return path


def load_registry(data_dir: Path) -> ModelRegistry:
    """Load ``models.yaml`` from ``data_dir``, writing the default on first run.

    Raises:
        RegistryError: The file is invalid.
    """
    return ModelRegistry.load(ensure_registry_file(data_dir))
