import re
from typing import Optional

from .runner import CommandRunner
from .errors import ParseError, CommandFailed
from .models import Portal, Target, Session, AuthCHAP


class ISCSIAdm:
    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner
        self.runner.require_binary("iscsiadm")

    def discovery_sendtargets(self, portal: Portal) -> list[Target]:
        """
        iscsiadm -m discovery -t sendtargets -p <ip:port>

        Typical output lines:
          10.0.0.10:3260,1 iqn.2000-01.com.synology:foo
          10.0.0.10:3260,1 iqn.2000-01.com.synology:bar
        """
        res = self.runner.run(
            ["iscsiadm", "-m", "discovery", "-t", "sendtargets", "-p", portal.address],
            timeout_s=30.0,
        )
        targets: list[Target] = []
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            # split into "<addr>,<tpgt> <iqn>"
            parts = line.split()
            if len(parts) < 2:
                raise ParseError(f"Unrecognized discovery line: {line}")
            addr_tpgt = parts[0]
            iqn = parts[1]
            addr = addr_tpgt.split(",")[0]
            ip, port_s = addr.rsplit(":", 1)
            try:
                port = int(port_s)
            except ValueError as e:
                raise ParseError(f"Bad port in discovery line: {line}") from e
            # ipv6: remove left/right brackets
            if ip.startswith('[') and ip.endswith(']'):
                ip = ip[1:-1]
            targets.append(Target(iqn=iqn, portal=Portal(ip=ip, port=port)))
        return targets

    def ensure_node_record(
        self,
        target: Target,
        *,
        startup: str = "manual",
    ) -> None:
        """
        Create node record + set startup policy.
        startup: manual | automatic
        """
        self._node_new(target)
        self._node_update(target, "node.startup", startup)

    def login_target(
        self,
        target: Target,
        *,
        auth: Optional[AuthCHAP] = None,
        startup: str = "manual",
    ) -> None:
        self.ensure_node_record(target, startup=startup)

        if auth:
            self._node_update(target, "node.session.auth.authmethod", "CHAP")
            self._node_update(target, "node.session.auth.username", auth.username)
            self._node_update(target, "node.session.auth.password", auth.password)

        self._node_login(target)

    def logout_target(self, target: Target) -> None:
        self._node_logout(target)

    def list_sessions(self) -> list[Session]:
        """
        iscsiadm -m session

        Typical line formats vary. Examples:
          tcp: [1] 10.0.0.10:3260,1 iqn.2000-01.com.synology:foo (non-flash)
          tcp: [2] 10.0.0.10:3260,1 iqn....
        """
        res = self.runner.run(["iscsiadm", "-m", "session"], check=False, timeout_s=10.0)

        if res.returncode != 0:
            # When there are no sessions, open-iscsi often returns non-zero with message.
            txt = (res.stdout + "\n" + res.stderr).lower()
            if "no active sessions" in txt or "no session" in txt:
                return []
            # otherwise treat as error
            self.runner.run(["iscsiadm", "-m", "session"], check=True, timeout_s=10.0)

        sessions: list[Session] = []
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line:
                continue

            # Try to capture session_id, portal, iqn
            # Pattern: "... [<id>] <ip>:<port>,<tpgt> <iqn>"
            m = re.search(r"\[(?P<sid>\d+)\]\s+(?P<addr>[^ ]+)\s+(?P<iqn>iqn\.[^\s]+)", line)
            if not m:
                # Fallback: parse without sid
                m2 = re.search(r"(?P<addr>\d+\.\d+\.\d+\.\d+:\d+),\d+\s+(?P<iqn>iqn\.[^\s]+)", line)
                if not m2:
                    continue
                addr = m2.group("addr")
                iqn = m2.group("iqn")
                ip, port_s = addr.rsplit(":", 1)
                sessions.append(
                    Session(
                        target=Target(
                            iqn=iqn,
                            portal=Portal(ip=ip, port=int(port_s))
                        )
                    )
                )
                continue

            sid = m.group("sid")
            addr_tpgt = m.group("addr")
            iqn = m.group("iqn")
            addr = addr_tpgt.split(",")[0]
            ip, port_s = addr.rsplit(":", 1)
            sessions.append(
                Session(
                    target=Target(
                        iqn=iqn,
                        portal=Portal(ip=ip, port=int(port_s))
                    ),
                    session_id=sid
                )
            )

        return sessions

    def rescan_sessions(self) -> None:
        # -R rescans all sessions
        self.runner.run(["iscsiadm", "-m", "session", "-R"], timeout_s=30.0)

    def _node_new(self, target: Target) -> None:
        """
        Create node record. If it already exists, open-iscsi often returns rc=15.
        We treat "already exists" as success.
        """
        try:
            self.runner.run(
                [
                    "iscsiadm",
                    "-m",
                    "node",
                    "-T",
                    target.iqn,
                    "-p",
                    target.portal.address,
                    "--op",
                    "new",
                ],
                timeout_s=15.0,
            )
        except CommandFailed as e:
            # rc may vary; stdout/stderr often includes "already exists"
            txt = (e.stdout + "\n" + e.stderr).lower()
            if "already exists" in txt or "exists" in txt:
                return
            raise

    def _node_update(self, target: Target, name: str, value: str) -> None:
        self.runner.run(
            [
                "iscsiadm",
                "-m",
                "node",
                "-T",
                target.iqn,
                "-p",
                target.portal.address,
                "--op",
                "update",
                "-n",
                name,
                "-v",
                value,
            ],
            timeout_s=15.0,
        )

    def _node_login(self, target: Target) -> None:
        """
        Login. If already logged in, open-iscsi often says so; treat as success.
        """
        try:
            self.runner.run(
                [
                    "iscsiadm",
                    "-m",
                    "node",
                    "-T",
                    target.iqn,
                    "-p",
                    target.portal.address,
                    "--login",
                ],
                timeout_s=30.0,
            )
        except CommandFailed as e:
            txt = (e.stdout + "\n" + e.stderr).lower()
            if "already present" in txt or "already logged in" in txt:
                return
            raise

    def _node_logout(self, target: Target) -> None:
        """
        Logout. If not logged in, treat as success.
        """
        try:
            self.runner.run(
                [
                    "iscsiadm",
                    "-m",
                    "node",
                    "-T",
                    target.iqn,
                    "-p",
                    target.portal.address,
                    "--logout",
                ],
                timeout_s=30.0,
            )
        except CommandFailed as e:
            txt = (e.stdout + "\n" + e.stderr).lower()
            if "no matching sessions" in txt or "not logged in" in txt:
                return
            raise