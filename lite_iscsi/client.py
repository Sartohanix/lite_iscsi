import time

from getpass import getpass
from typing import Any, Optional

from .core.runner import CommandRunner

from .core.iscsiadm import ISCSIAdm
from .core.models import Portal, Target, Session, LunDevice, AuthCHAP
from .core.models import parse_target, parse_auth

from .linux.devlinks import list_luns_by_path
from .linux.sysfs import list_luns_sysfs_fallback
from .linux.udev import udev_settle


class InitiatorClient:
    def __init__(self,
        *,
        sudo_mode: str = "non-interactive",
        sudo_password: str | None = None,
    ) -> None:
        self.runner = CommandRunner(sudo_mode=sudo_mode, sudo_password=sudo_password)
        self.iscsiadm = ISCSIAdm(self.runner)

    @classmethod
    def with_sudo_prompt(cls) -> InitiatorClient:
        pw = getpass("sudo password: ")
        return cls(sudo_mode="stdin", sudo_password=pw)

    def discover(self, portal_ip: str, port: int = 3260,
                 strict_ip: bool = False,
                 iqn_contains : Optional[str] = None) -> list[Target]:
        targets = self.iscsiadm.discovery_sendtargets(Portal(ip=portal_ip, port=port))

        if strict_ip:
            targets = [t for t in targets if t.portal.ip == portal_ip]
        if iqn_contains and isinstance(iqn_contains, str):
            targets = [t for t in targets if iqn_contains in t.iqn]

        return targets

    def login(
        self,
        target: Target | dict[str, Any],
        auth: Optional[AuthCHAP | dict[str, str]] = None,
        startup: str = "manual") -> Session | None:
        """
        `target` is either
            - A `Target` dataclass object: `Target(iqn=<...>, portal=Portal(ip=<...>, port=<...>))` ;
            - Equivalently, a dictionary of the form `{'iqn': <...>, 'portal': <...>}` ;
            - A more explicit dictionary of the form `{'iqn': <...>, 'ip': <...>, 'port': <...>}` ;
            - Similar to above, but with default port: `{'iqn': <...>, 'ip': <...>}`.

        `auth` is either
            - A `AuthCHAP` dataclass object: `AuthCHAP(username=<...>, password=<...>)`
            - Equivalently, a dictionary of the form `{'username': <...>, 'password': <...>}`.
        """

        target = parse_target(target)
        auth = parse_auth(auth)
        self.iscsiadm.login_target(target, auth=auth, startup=startup)

        # Let udev settle so /dev/disk/by-path shows up reliably
        udev_settle(self.runner, timeout_s=10.0)

        return self.get_active_session(target)

    def logout(self, target: Target | dict[str, Any]) -> None:
        target = parse_target(target)
        self.iscsiadm.logout_target(target)
        udev_settle(self.runner, timeout_s=5.0)

    def get_active_session(self, target: Target) -> Session | None:
        """ Returns a session object for the provided target. If none found, return None."""
        for s in self.sessions():
            if s.target == target:
                return s
        return None

    def sessions(self) -> list[Session]:
        return self.iscsiadm.list_sessions()

    def rescan(self) -> None:
        self.iscsiadm.rescan_sessions()
        udev_settle(self.runner, timeout_s=10.0)

    def luns(
        self,
        session_or_target: Optional[Session | Target | dict[str, Any]],
        *,
        allow_sysfs_fallback: bool = True,
        timeout_s: float = 5.0,
        poll_s: float = 0.5,
    ) -> list[LunDevice]:

        if not session_or_target:
            return []

        if isinstance(session_or_target, Session):
            target = session_or_target.target
        else:
            target = parse_target(session_or_target)

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            luns = self._luns(target, allow_sysfs_fallback=allow_sysfs_fallback)
            if luns:
                return luns
            time.sleep(poll_s)
        return []

    def _luns(
        self,
        target: Target | dict[str, Any],
        *,
        allow_sysfs_fallback: bool = True,
    ) -> list[LunDevice]:

        target = parse_target(target)

        # Primary: stable by-path links
        by_path = list_luns_by_path(target)
        if by_path:
            return by_path

        if not allow_sysfs_fallback:
            return []

        # Fallback: sysfs traversal (less stable across distros)
        return list_luns_sysfs_fallback(target)
