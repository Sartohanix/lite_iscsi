from __future__ import annotations

import glob
import os
import re

from ..core.models import Target, LunDevice


_BY_PATH_DIR = "/dev/disk/by-path"


def _by_path_pattern(target: Target) -> str:
    # Example:
    # /dev/disk/by-path/ip-10.0.0.10:3260-iscsi-iqn....-lun-0
    # Some distros may include "-p 1" variants, but this is the common form.
    return os.path.join(_BY_PATH_DIR, f"ip-{target.portal.ip}:{target.portal.port}-iscsi-{target.iqn}-lun-*")


def list_luns_by_path(target: Target) -> list[LunDevice]:
    pat = _by_path_pattern(target)
    paths = sorted(glob.glob(pat))
    out: list[LunDevice] = []

    for p in paths:
        base = os.path.basename(p)
        m = re.search(r"-lun-(\d+)$", base)
        if not m:
            continue
        lun = int(m.group(1))

        real_device = None
        try:
            # Resolve symlink to /dev/sdX (or similar)
            real = os.path.realpath(p)
            if real.startswith("/dev/"):
                real_device = real
        except OSError:
            real_device = None

        out.append(
            LunDevice(
                target=target,
                lun=lun,
                by_path=p,
                real_device=real_device,
            )
        )

    return out
