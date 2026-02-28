import time

from ..core.runner import CommandRunner


def udev_settle(runner: CommandRunner, timeout_s: float = 10.0) -> None:
    """
    Best-effort: if udevadm exists, wait for device events to settle.
    """
    try:
        runner.require_binary("udevadm")
    except Exception:
        return

    runner.run(["udevadm", "settle", f"--timeout={int(timeout_s)}"], check=False, timeout_s=timeout_s + 2.0)


def wait_for_path(path: str, *, timeout_s: float = 30.0, poll_s: float = 0.2) -> bool:
    import os

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if os.path.exists(path):
            return True
        time.sleep(poll_s)
    return False
