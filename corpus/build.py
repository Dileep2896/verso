"""Build the corpus from corpus/manifest.yaml.

Writes:
    corpus/build/attacks/<id>.pdf     one labeled adversarial PDF per case
    corpus/build/clean/<id>.pdf       clean controls
    corpus/build/labels.json          machine-resolved ground truth (exact bboxes)

Deterministic: every case takes its seed from the manifest and /Info dates + the
file /ID are normalized, so a clean checkout reproduces byte-identical files.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from .forge import GENERATORS
from .forge.clean import build_clean
from .forge.hosts import generate_host
from .forge.inject_util import normalize

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "manifest.yaml"
BUILD = ROOT / "build"
ATTACKS = BUILD / "attacks"
CLEAN = BUILD / "clean"


def main() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text())
    payloads = manifest["payloads"]

    ATTACKS.mkdir(parents=True, exist_ok=True)
    CLEAN.mkdir(parents=True, exist_ok=True)

    # cache host bytes (generated once, reused across cases)
    host_cache: dict[str, bytes] = {k: generate_host(k) for k in manifest["hosts"]}

    labels = {"attacks": [], "clean": []}

    # -- clean controls ----------------------------------------------------- #
    for entry in manifest["clean"]:
        cid, kind = entry["id"], entry["kind"]
        data = normalize(build_clean(kind))
        (CLEAN / f"{cid}.pdf").write_bytes(data)
        labels["clean"].append({"id": cid, "kind": kind, "file": f"clean/{cid}.pdf"})
        print(f"  clean  {cid:22} {kind}")

    # -- attack cases ------------------------------------------------------- #
    for case in manifest["cases"]:
        cid = case["id"]
        cls = case["class"]
        host = case["host"]
        seed = int(case["seed"])
        mechanism = case["mechanism"]
        payload = payloads[int(case["payload"])]
        page = int(case.get("page", 0))

        inject = GENERATORS[cls]
        raw, gt = inject(host_cache[host], payload, seed, mechanism, page)
        data = normalize(raw)
        fname = f"{cid}.pdf"
        (ATTACKS / fname).write_bytes(data)

        labels["attacks"].append({
            "id": cid, "attack_class": cls, "host": host, "seed": seed,
            "mechanism": mechanism, "payload": payload,
            "page": gt["page"], "bbox": gt["bbox"], "note": gt["note"],
            "file": f"attacks/{fname}",
        })
        print(f"  {cls}     {cid:22} {host:8} {mechanism}")

    (BUILD / "labels.json").write_text(json.dumps(labels, indent=2, sort_keys=True))
    n_attacks = len(labels["attacks"])
    n_clean = len(labels["clean"])
    print(f"\nbuilt {n_attacks} attack cases + {n_clean} clean controls "
          f"-> {BUILD}")


if __name__ == "__main__":
    main()
