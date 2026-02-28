import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Sequence

from .errors import CommandFailed, CommandNotFound, PermissionError, TimeoutError


@dataclass(frozen=True)
class RunResult:
    cmd: list[str]
    returncode: int
    stdout: str
    stderr: str


class CommandRunner:
    """
    sudo_mode:
      - "none": never sudo
      - "non-interactive": sudo -n (fail if password required)   [good for automation]
      - "stdin": sudo -S (read password from stdin)              [works in Jupyter]
      - "tty": sudo (prompt on tty)                              [works in real terminals]
    """

    def __init__(
        self,
        *,
        sudo_mode: str = "non-interactive",
        sudo_path: str = "sudo",
        sudo_password: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.sudo_mode = sudo_mode
        self.sudo_path = sudo_path
        self.sudo_password = sudo_password
        self.env = env

        if self.sudo_mode != "none" and not shutil.which(self.sudo_path):
            raise CommandNotFound(f"sudo not found: {self.sudo_path}")

    @staticmethod
    def require_binary(name: str) -> None:
        if not shutil.which(name):
            raise CommandNotFound(f"Required binary not found in PATH: {name}")

    def _sudo_prefix(self) -> list[str]:
        if self.sudo_mode == "none" or os.geteuid() == 0:
            return []
        if self.sudo_mode == "non-interactive":
            return [self.sudo_path, "-n", "--"]
        if self.sudo_mode == "stdin":
            # -S reads from stdin; -p "" suppresses prompt text
            return [self.sudo_path, "-S", "-p", "", "--"]
        if self.sudo_mode == "tty":
            return [self.sudo_path, "--"]
        raise ValueError(f"Unknown sudo_mode: {self.sudo_mode}")

    def run(
        self,
        cmd: Sequence[str],
        *,
        check: bool = True,
        timeout_s: float | None = 5.0,
        capture: bool = True,
    ) -> RunResult:
        full_cmd = self._sudo_prefix() + list(cmd)

        # If using sudo -S, feed password to stdin.
        stdin_data: str | None = None
        if self.sudo_mode == "stdin" and os.geteuid() != 0:
            if not self.sudo_password:
                # Let sudo fail with a useful message rather than guessing
                stdin_data = ""
            else:
                stdin_data = self.sudo_password + "\n"

        try:
            proc = subprocess.run(
                full_cmd,
                check=False,
                timeout=timeout_s,
                text=True,
                input=stdin_data,
                capture_output=capture,
                env=self.env,
            )
        except subprocess.TimeoutExpired as e:
            raise TimeoutError(f"Command timed out: {full_cmd}") from e
        except FileNotFoundError as e:
            raise CommandNotFound(f"Command not found: {full_cmd[:1]}") from e

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""

        if check and proc.returncode != 0:
            lower = (stderr + stdout).lower()
            if "permission denied" in lower or "must be root" in lower:
                raise PermissionError(f"Insufficient privileges for: {full_cmd}")

            raise CommandFailed(
                message=f"Command failed (rc={proc.returncode}): {full_cmd}",
                returncode=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                cmd=full_cmd,
            )

        return RunResult(
            cmd=full_cmd,
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
        )