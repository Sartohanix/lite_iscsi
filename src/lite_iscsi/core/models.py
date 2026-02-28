from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class Portal:
    ip: str
    port: int = 3260

    @property
    def address(self) -> str:
        return f"{self.ip}:{self.port}"


@dataclass(frozen=True)
class Target:
    iqn: str
    portal: Portal


@dataclass(frozen=True)
class Session:
    target: Target
    session_id: str | None = None


@dataclass(frozen=True)
class LunDevice:
    """
    Represents a single LUN's exposed block device.

    Prefer by-path because it is stable across reboots and device renames:
      /dev/disk/by-path/ip-...-iscsi-...-lun-<n>
    """
    target: Target
    lun: int
    by_path: str
    real_device: str | None = None  # e.g. /dev/sdb, resolved from symlink


@dataclass(frozen=True)
class AuthCHAP:
    username: str
    password: str


def parse_target(target: Target | dict[str, Any]) -> Target:
    """
    `target` is either
        - A `Target` dataclass object: `Target(iqn=<...>, portal=Portal(ip=<...>, port=<...>))` ;
        - Equivalently, a dictionary of the form `{'iqn': <...>, 'portal': <...>}` ;
        - A more explicit dictionary of the form `{'iqn': <...>, 'ip': <...>, 'port': <...>}` ;
        - Similar to above, but with default port: `{'iqn': <...>, 'ip': <...>}`.
    """

    if isinstance(target, dict):
        tkeys = target.keys()
        if tkeys == {'iqn', 'portal'}:
            if isinstance(target['portal'], Portal):
                return Target(iqn=target['iqn'], portal=target['portal'])
            else:
                raise ValueError(' ... ')
        elif tkeys == {'iqn', 'ip', 'port'}:
            return Target(iqn=target['iqn'], portal=Portal(ip=target['ip'], port=target['port']))
        elif tkeys == {'iqn', 'ip'}:
            return Target(iqn=target['iqn'], portal=Portal(ip=target['ip'])) # Default port
        raise KeyError(' ... ')
    elif isinstance(target, Target):
        return target

    raise ValueError(' ... ')

def parse_auth(auth: Optional[AuthCHAP | dict[str, str]]) -> Optional[AuthCHAP]:
    """
    `auth` is either
        - A `AuthCHAP` dataclass object: `AuthCHAP(username=<...>, password=<...>)`
        - Equivalently, a dictionary of the form `{'username': <...>, 'password': <...>}`.
        - None
    """
    if auth:
        if isinstance(auth, dict):
            if auth.keys() == {'username', 'password'}:
                return AuthCHAP(username=auth['username'], password=auth['password'])
            else:
                raise KeyError(' ... ')
        elif isinstance(auth, AuthCHAP):
            return auth
        raise ValueError(' ... ')
    return None
