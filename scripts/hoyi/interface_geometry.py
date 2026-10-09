from pathlib import Path
from math import sqrt


def _parse_pdb(path):
    atoms = []

    with open(path) as f:
        for line in f:
            if not line.startswith(("ATOM  ", "HETATM")):
                continue

            try:
                atom = line[12:16].strip()
                chain = line[21].strip()
                resi = int(line[22:26])
                x = float(line[30:38])
                y = float(line[38:46])
                z = float(line[46:54])
            except Exception:
                continue

            # 忽略氢原子
            if atom.startswith("H"):
                continue

            atoms.append({
                "atom": atom,
                "chain": chain,
                "resi": resi,
                "xyz": (x, y, z),
            })

    return atoms


def _dist(a, b):
    return sqrt(
        (a[0] - b[0]) ** 2
        + (a[1] - b[1]) ** 2
        + (a[2] - b[2]) ** 2
    )


def analyze_interface(
    pdb_path,
    target_chain="A",
    hotspot_res=None,
    interface_cutoff=6.0,
):
    """
    计算 target-binder 界面几何。

    Ring3.5 v1:
    - 仅做几何诊断
    - hard gate 只过滤明显无界面的结构
    - 暂不使用未经校准的加权 interface score
    """

    pdb_path = Path(pdb_path)
    hotspot_res = set(hotspot_res or [])

    atoms = _parse_pdb(pdb_path)

    target_atoms = [
        a for a in atoms
        if a["chain"] == target_chain
    ]

    binder_atoms = [
        a for a in atoms
        if a["chain"] != target_chain
    ]

    if not target_atoms:
        raise ValueError(
            f"{pdb_path.name}: 未找到 target chain {target_chain}"
        )

    if not binder_atoms:
        raise ValueError(
            f"{pdb_path.name}: 未找到 binder chain"
        )

    min_dist = float("inf")

    contacts = {
        4.0: 0,
        6.0: 0,
        8.0: 0,
    }

    target_if = set()
    binder_if = set()

    hotspot_min = {
        h: float("inf")
        for h in hotspot_res
    }

    hotspot_contacts = {
        h: 0
        for h in hotspot_res
    }

    for ta in target_atoms:
        for ba in binder_atoms:
            d = _dist(
                ta["xyz"],
                ba["xyz"],
            )

            min_dist = min(min_dist, d)

            if d <= 4.0:
                contacts[4.0] += 1

            if d <= 6.0:
                contacts[6.0] += 1

            if d <= 8.0:
                contacts[8.0] += 1

            if d <= interface_cutoff:
                target_if.add(
                    (ta["chain"], ta["resi"])
                )
                binder_if.add(
                    (ba["chain"], ba["resi"])
                )

            if ta["resi"] in hotspot_res:
                hotspot_min[ta["resi"]] = min(
                    hotspot_min[ta["resi"]],
                    d,
                )

                if d <= interface_cutoff:
                    hotspot_contacts[
                        ta["resi"]
                    ] += 1

    binder_if_res = len(binder_if)
    target_if_res = len(target_if)

    # v1只过滤极端异常：
    # 完全没有6 Å界面接触，或binder没有任何界面残基
    hard_pass = (
        contacts[6.0] > 0
        and binder_if_res > 0
    )

    return {
        "pdb": str(pdb_path),
        "target_chain": target_chain,
        "min_dist": round(min_dist, 3),
        "contacts_4A": contacts[4.0],
        "contacts_6A": contacts[6.0],
        "contacts_8A": contacts[8.0],
        "target_if_res": target_if_res,
        "binder_if_res": binder_if_res,
        "hotspot_min_dist": {
            str(h): (
                None
                if hotspot_min[h] == float("inf")
                else round(hotspot_min[h], 3)
            )
            for h in sorted(hotspot_res)
        },
        "hotspot_contacts": {
            str(h): hotspot_contacts[h]
            for h in sorted(hotspot_res)
        },
        "hotspot_contacts_total": sum(
            hotspot_contacts.values()
        ),
        "hard_pass": hard_pass,
    }
