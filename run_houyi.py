#!/usr/bin/env python3

import argparse
import os

from scripts.hoyi.config import Config
from scripts.hoyi import run_pipeline
from scripts.hoyi import ring1


def preflight(cfg, organism):
    print("===== HOUYI PRODUCTION PREFLIGHT =====")
    print("organism =", organism)

    cfg.set_organism(organism)

    # 1. 自动选靶
    r1 = ring1.run(
        cfg,
        organism,
        targets_filter=None,
        dry_run=True,
        auto_top_n_targets=1,
    )

    targets = r1.get("targets", [])
    if not targets:
        raise RuntimeError("Preflight failed: no target selected")

    target = targets[0]
    meta = (r1.get("target_meta") or {}).get(target, {})

    print("auto_target =", target)
    print("protein =", meta.get("protein"))
    print("length_aa =", meta.get("length_aa"))

    # 2. 序列检查
    seq = meta.get("sequence") or ""
    if not seq:
        raise RuntimeError(
            f"Preflight failed: {target} has no sequence"
        )
    print("sequence =", f"OK ({len(seq)} aa)")

    # 3. 结构路线检查
    pdb = meta.get("pdb")
    if pdb:
        print("structure_route =", f"PDB {pdb}")
    else:
        print("structure_route =", "Chai-1 prediction")

    # 4. RFdiffusion checkpoint
    rf_ckpt = os.environ.get(
        "HOUYI_RF_CKPT",
        getattr(cfg, "rf_ckpt", None),
    )
    if rf_ckpt and os.path.exists(rf_ckpt):
        print("RFdiffusion_checkpoint = OK")
    else:
        print("RFdiffusion_checkpoint = CHECK")
        print("  path =", rf_ckpt)

    # 5. ProteinMPNN
    mpnn_root = os.environ.get("HOUYI_MPNN_ROOT")
    if mpnn_root and os.path.isdir(mpnn_root):
        print("ProteinMPNN = OK")
    else:
        print("ProteinMPNN = CHECK")
        print("  path =", mpnn_root)

    # 6. AF2 / ColabFold
    colabfold_bin = os.environ.get("HOUYI_COLABFOLD_BIN")
    if colabfold_bin and os.path.exists(colabfold_bin):
        print("ColabFold = OK")
    else:
        print("ColabFold = CHECK")
        print("  path =", colabfold_bin)

    print()
    print("===== PLANNED PRODUCTION WORKFLOW =====")
    print("Ring1  auto target selection")
    print("Ring2  structure retrieval/prediction")
    print("Ring3  RFdiffusion de novo binder")
    print("Ring3.5 geometry gate")
    print("Ring4  ProteinMPNN + ESM scoring")
    print("Ring4.5 AF2 validation")
    print("Ring5  multi-evidence selection")
    print("Ring6  payload assembly")
    print("Ring7  surface receptor selection")
    print("Ring8  natural/de novo fiber route")
    print("Ring9  pvc13 reprogramming")
    print("Ring10 final nanosyringe assembly")

    print()
    print("HOUYI_PREFLIGHT_PASS")


def main():
    parser = argparse.ArgumentParser(
        description="HOUYI end-to-end antibacterial nanosyringe design"
    )

    parser.add_argument(
        "organism",
        help='Pathogen name, e.g. "Staphylococcus aureus"',
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run fast production preflight without heavy computation",
    )

    args = parser.parse_args()
    cfg = Config()

    if args.dry_run:
        preflight(cfg, args.organism)
        return

    state = run_pipeline(
        cfg=cfg,
        organism=args.organism,

        targets=None,
        auto_top_n_targets=1,

        start=1,
        stop=10,
        skip=None,
        dry_run=False,

        scorer="mpnn_esm",
        top_n=3,
        num_designs=1,
        mpnn_samples=1,

        af2_validate=True,
        af2_top_k=3,
        af2_models=5,
        af2_seeds=3,
        af2_recycles=6,

        force_de_novo=True,
    )

    print("\n===== HOUYI FINAL SUMMARY =====")

    rings = state.get("rings", {})

    for i in range(1, 11):
        r = rings.get(str(i), {})
        print(
            f"Ring {i}:",
            r.get("status"),
            "|",
            r.get("info"),
        )

    print("\nHOUYI_ONE_INPUT_WORKFLOW_DONE")


if __name__ == "__main__":
    main()
