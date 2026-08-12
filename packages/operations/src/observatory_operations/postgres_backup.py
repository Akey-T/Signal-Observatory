"""Official PostgreSQL backup tooling with local and Docker discovery."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy.engine import URL, make_url


class PostgresToolError(RuntimeError):
    """Raised when an official PostgreSQL utility cannot complete safely."""


class PostgresTool(Protocol):
    def client_version(self) -> str: ...

    def dump(self, database_url: str, target: Path, *, snapshot: str | None = None) -> None: ...

    def validate_dump(self, dump_path: Path) -> None: ...

    def restore(self, database_url: str, dump_path: Path) -> None: ...


@dataclass(frozen=True, slots=True)
class ConnectionParts:
    username: str
    password: str | None
    host: str | None
    port: int | None
    database: str


class PostgresBackupTool:
    """Wrap pg_dump/pg_restore without exposing connection secrets in output."""

    def __init__(
        self,
        *,
        mode: str,
        repository_root: Path,
        pg_dump: str = "pg_dump",
        pg_restore: str = "pg_restore",
        docker: str | None = None,
    ) -> None:
        self.mode = mode
        self.repository_root = repository_root
        self.pg_dump = pg_dump
        self.pg_restore = pg_restore
        self.docker = docker

    @classmethod
    def discover(cls, repository_root: Path) -> PostgresBackupTool:
        pg_dump = shutil.which("pg_dump")
        pg_restore = shutil.which("pg_restore")
        if pg_dump and pg_restore:
            return cls(
                mode="local",
                repository_root=repository_root,
                pg_dump=pg_dump,
                pg_restore=pg_restore,
            )
        docker = shutil.which("docker")
        common = Path("C:/Program Files/Docker/Docker/resources/bin/docker.exe")
        if docker is None and common.is_file():
            docker = str(common)
        if docker is None:
            raise PostgresToolError("pg_dump/pg_restore and Docker are unavailable")
        return cls(mode="docker", repository_root=repository_root, docker=docker)

    def client_version(self) -> str:
        command = (
            [self.pg_dump, "--version"]
            if self.mode == "local"
            else self._docker_prefix() + ["pg_dump", "--version"]
        )
        result = self._run(command)
        match = re.search(r"(\d+(?:\.\d+)*)", result.stdout.decode(errors="replace"))
        if match is None:
            raise PostgresToolError("could not parse pg_dump version")
        return match.group(1)

    def dump(self, database_url: str, target: Path, *, snapshot: str | None = None) -> None:
        parts = self._parts(database_url)
        target.parent.mkdir(parents=True, exist_ok=True)
        args = ["-Fc", "--no-owner", "--no-privileges"]
        if snapshot:
            args.append(f"--snapshot={snapshot}")
        command, environment = self._command("pg_dump", parts, args)
        with target.open("wb") as output:
            process = subprocess.run(
                command,
                cwd=self.repository_root,
                env=environment,
                stdout=output,
                stderr=subprocess.PIPE,
                check=False,
            )
        if process.returncode != 0:
            target.unlink(missing_ok=True)
            raise PostgresToolError(self._safe_error("pg_dump failed", process.stderr))

    def validate_dump(self, dump_path: Path) -> None:
        if self.mode == "local":
            result = self._run([self.pg_restore, "--list", str(dump_path)])
        else:
            result = self._run(
                self._docker_prefix() + ["pg_restore", "--list"],
                input_bytes=dump_path.read_bytes(),
            )
        if not result.stdout.strip():
            raise PostgresToolError("pg_restore --list returned an empty catalog")

    def restore(self, database_url: str, dump_path: Path) -> None:
        parts = self._parts(database_url)
        args = ["--exit-on-error", "--no-owner", "--no-privileges"]
        command, environment = self._command("pg_restore", parts, args)
        result = subprocess.run(
            command,
            cwd=self.repository_root,
            env=environment,
            input=dump_path.read_bytes(),
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise PostgresToolError(self._safe_error("pg_restore failed", result.stderr))

    def _command(
        self, utility: str, parts: ConnectionParts, args: list[str]
    ) -> tuple[list[str], dict[str, str]]:
        environment = dict(os.environ)
        if self.mode == "local":
            executable = self.pg_dump if utility == "pg_dump" else self.pg_restore
            command = [executable, *args]
            if parts.host:
                command.extend(["-h", parts.host])
            if parts.port:
                command.extend(["-p", str(parts.port)])
            command.extend(["-U", parts.username, "-d", parts.database])
            if parts.password:
                environment["PGPASSWORD"] = parts.password
            return command, environment

        remote = parts.host not in {None, "localhost", "127.0.0.1", "db"}
        command = self._docker_prefix(password=parts.password if remote else None)
        command.extend([utility, *args, "-U", parts.username, "-d", parts.database])
        if remote:
            assert parts.host is not None
            command.extend(["-h", parts.host])
        if parts.port and remote:
            command.extend(["-p", str(parts.port)])
        return command, environment

    def _docker_prefix(self, *, password: str | None = None) -> list[str]:
        if self.docker is None:
            raise PostgresToolError("Docker executable is unavailable")
        command = [self.docker, "compose", "exec", "-T"]
        if password:
            command.extend(["-e", f"PGPASSWORD={password}"])
        return [*command, "db"]

    def _run(
        self, command: list[str], *, input_bytes: bytes | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        result = subprocess.run(
            command,
            cwd=self.repository_root,
            input=input_bytes,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise PostgresToolError(self._safe_error("PostgreSQL utility failed", result.stderr))
        return result

    @staticmethod
    def _parts(database_url: str) -> ConnectionParts:
        url: URL = make_url(database_url)
        if not url.drivername.startswith("postgresql") or not url.database or not url.username:
            raise PostgresToolError("backup requires an explicit PostgreSQL database URL")
        return ConnectionParts(
            username=url.username,
            password=url.password,
            host=url.host,
            port=url.port,
            database=url.database,
        )

    @staticmethod
    def _safe_error(prefix: str, stderr: bytes) -> str:
        message = stderr.decode(errors="replace").strip().splitlines()
        return f"{prefix}: {message[-1] if message else 'unknown error'}"


def assert_version_compatible(client_version: str, server_version_num: int) -> None:
    client_major = int(client_version.split(".", 1)[0])
    server_major = server_version_num // 10000
    if client_major < server_major:
        raise PostgresToolError(
            f"pg_dump major {client_major} is older than PostgreSQL server major {server_major}"
        )
