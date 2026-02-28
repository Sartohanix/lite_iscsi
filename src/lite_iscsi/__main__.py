from __future__ import annotations

import argparse
import json
import sys

from .client import InitiatorClient

def _print(obj, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, indent=2, sort_keys=True))
    else:
        print(obj)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="iscsi-init", description="Minimal iSCSI initiator helper (open-iscsi).")
    parser.add_argument(
        "--sudo-mode",
        default="non-interactive",
        choices=["none", "non-interactive", "stdin", "tty"],
        help="Sudo behavior: none, non-interactive (default), stdin, or tty.",
    )
    parser.add_argument("--sudo-password", default=None, help="Password for sudo_mode=stdin.")
    parser.add_argument("--sudo-prompt", action="store_true", help="Prompt for sudo password and use sudo_mode=stdin.")
    parser.add_argument("--no-sudo", action="store_true", help="Shortcut for --sudo-mode=none.")
    parser.add_argument("--json", action="store_true", help="Output JSON where applicable.")

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_disc = sub.add_parser("discover", help="Discover targets on a portal.")
    p_disc.add_argument("portal_ip")
    p_disc.add_argument("--port", type=int, default=3260)
    p_disc.add_argument("--strict-ip", action="store_true")
    p_disc.add_argument("--iqn-contains", default=None)

    p_login = sub.add_parser("login", help="Login to a target.")
    p_login.add_argument("portal_ip")
    p_login.add_argument("target_iqn")
    p_login.add_argument("--port", type=int, default=3260)
    p_login.add_argument("--startup", default="manual", choices=["manual", "automatic"])
    p_login.add_argument("--chap-user", default=None)
    p_login.add_argument("--chap-pass", default=None)

    p_logout = sub.add_parser("logout", help="Logout from a target.")
    p_logout.add_argument("portal_ip")
    p_logout.add_argument("target_iqn")
    p_logout.add_argument("--port", type=int, default=3260)

    sub.add_parser("sessions", help="List active iSCSI sessions.")
    sub.add_parser("rescan", help="Rescan all sessions for new LUNs.")

    p_luns = sub.add_parser("luns", help="List LUN devices for a target (by-path).")
    p_luns.add_argument("portal_ip")
    p_luns.add_argument("target_iqn")
    p_luns.add_argument("--port", type=int, default=3260)

    p_wait = sub.add_parser("wait-luns", help="Wait for LUNs to appear (polling).")
    p_wait.add_argument("portal_ip")
    p_wait.add_argument("target_iqn")
    p_wait.add_argument("--port", type=int, default=3260)
    p_wait.add_argument("--allow-sysfs-fallback", action="store_true")
    p_wait.add_argument("--poll", type=float, default=0.5)
    p_wait.add_argument("--timeout", type=float, default=30.0)

    p_luns.add_argument("--allow-sysfs-fallback", action="store_true")
    p_luns.add_argument("--poll", type=float, default=0.5)
    p_luns.add_argument("--timeout", type=float, default=5.0)

    args = parser.parse_args(argv)

    if args.sudo_prompt:
        client = InitiatorClient.with_sudo_prompt()
    else:
        sudo_mode = "none" if args.no_sudo else args.sudo_mode
        client = InitiatorClient(sudo_mode=sudo_mode, sudo_password=args.sudo_password)

    if args.cmd == "discover":
        targets = client.discover(
            args.portal_ip,
            args.port,
            strict_ip=args.strict_ip,
            iqn_contains=args.iqn_contains,
        )
        payload = [{"iqn": t.iqn, "portal": t.portal.address} for t in targets]
        _print(payload, args.json)
        return 0

    if args.cmd == "login":
        auth = None
        if args.chap_user is not None or args.chap_pass is not None:
            if not args.chap_user or not args.chap_pass:
                print("Both --chap-user and --chap-pass are required for CHAP.", file=sys.stderr)
                return 2
            auth = {"username": args.chap_user, "password": args.chap_pass}

        target = {"iqn": args.target_iqn, "ip": args.portal_ip, "port": args.port}
        session = client.login(target, auth=auth, startup=args.startup)
        payload = (
            {
                "iqn": session.target.iqn,
                "portal": session.target.portal.address,
                "session_id": session.session_id,
            }
            if session
            else None
        )
        _print(payload if args.json else "OK", args.json)
        return 0

    if args.cmd == "logout":
        target = {"iqn": args.target_iqn, "ip": args.portal_ip, "port": args.port}
        client.logout(target)
        _print("OK", args.json)
        return 0

    if args.cmd == "sessions":
        sessions = client.sessions()
        payload = [
            {
                "iqn": s.target.iqn,
                "portal": s.target.portal.address,
                "session_id": s.session_id,
            }
            for s in sessions
        ]
        _print(payload, args.json)
        return 0

    if args.cmd == "rescan":
        client.rescan()
        _print("OK", args.json)
        return 0

    if args.cmd == "luns":
        target = {"iqn": args.target_iqn, "ip": args.portal_ip, "port": args.port}
        luns = client.luns(
            target,
            allow_sysfs_fallback=args.allow_sysfs_fallback,
            timeout_s=args.timeout,
            poll_s=args.poll,
        )
        payload = [
            {
                "lun": d.lun,
                "by_path": d.by_path,
                "real_device": d.real_device,
            }
            for d in luns
        ]
        _print(payload, args.json)
        return 0

    if args.cmd == "wait-luns":
        target = {"iqn": args.target_iqn, "ip": args.portal_ip, "port": args.port}
        luns = client.luns(
            target,
            allow_sysfs_fallback=args.allow_sysfs_fallback,
            timeout_s=args.timeout,
            poll_s=args.poll,
        )
        payload = [
            {
                "lun": d.lun,
                "by_path": d.by_path,
                "real_device": d.real_device,
            }
            for d in luns
        ]
        _print(payload, args.json)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
