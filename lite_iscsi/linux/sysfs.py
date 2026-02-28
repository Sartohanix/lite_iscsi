import os
from dataclasses import dataclass

from ..core.models import Target, LunDevice


@dataclass(frozen=True)
class SysfsLun:
    lun: int
    block: str  # e.g. "sdb"


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def _safe_listdir(path: str) -> list[str]:
    try:
        return os.listdir(path)
    except FileNotFoundError:
        return []


def list_luns_sysfs_fallback(target: Target) -> list[LunDevice]:
    """
    Fallback LUN enumeration via sysfs.

    Sysfs layout can vary; this function is deliberately conservative and may return fewer results
    than /dev/disk/by-path on some distros.

    Strategy:
      - Walk /sys/class/iscsi_session/session*/device and find block devices underneath.
      - We do not perfectly prove which session belongs to which (portal, iqn) in all cases;
        instead we attempt best-effort filtering by reading known attributes when available.
    """
    sessions_dir = "/sys/class/iscsi_session"
    out: list[LunDevice] = []

    for sess in _safe_listdir(sessions_dir):
        if not sess.startswith("session"):
            continue

        dev_root = os.path.join(sessions_dir, sess, "device")
        if not os.path.isdir(dev_root):
            continue

        # Best-effort filter: look for "targetname" or similar
        # (Not always present; skip filtering if unknown)
        matches = True
        tgtname_path = os.path.join(dev_root, "targetname")
        if os.path.exists(tgtname_path):
            try:
                matches = (_read_text(tgtname_path) == target.iqn)
            except Exception:
                matches = True

        if not matches:
            continue

        # Find "block" directories in subtree:
        # .../device/targetH:B:I/H:B:I:L/block/sdX
        for root, dirs, _files in os.walk(dev_root):
            if "block" not in dirs:
                continue
            block_dir = os.path.join(root, "block")
            for blk in _safe_listdir(block_dir):
                # LUN number is often the last component in ".../H:B:I:L"
                lun = None
                parent = os.path.basename(os.path.dirname(block_dir))
                # parent might look like "0:0:0:1"
                parts = parent.split(":")
                if len(parts) == 4 and all(p.isdigit() for p in parts):
                    lun = int(parts[3])
                if lun is None:
                    continue

                by_path_guess = ""
                real_device = f"/dev/{blk}"
                out.append(
                    LunDevice(
                        target=target,
                        lun=lun,
                        by_path=by_path_guess,
                        real_device=real_device,
                    )
                )

    # Deduplicate by (lun, real_device)
    seen: set[tuple[int, str | None]] = set()
    uniq: list[LunDevice] = []
    for d in out:
        key = (d.lun, d.real_device)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(d)
    return sorted(uniq, key=lambda x: x.lun)
