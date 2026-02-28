
class ISCSIError(Exception):
    """Base class for iSCSI initiator errors."""


class CommandNotFound(ISCSIError):
    pass


class CommandFailed(ISCSIError):
    def __init__(
        self,
        message: str,
        returncode: int,
        stdout: str | None = None,
        stderr: str | None = None,
        cmd: list[str] | None = None,
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout or ""
        self.stderr = stderr or ""
        self.cmd = cmd or []

        super().__init__(message + "\nStdout = \n" + self.stdout + "\nStderr = \n" + self.stderr)


class PermissionError(ISCSIError):
    pass


class TimeoutError(ISCSIError):
    pass


class ParseError(ISCSIError):
    pass
