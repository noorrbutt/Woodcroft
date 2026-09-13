"""Preview the plate generator before committing to a full seed run.

    python -m app.services.media --preview

Writes a dozen sample plates and one swatch per species into media/_preview/,
so the look can be checked in a few seconds rather than after a four minute
seed.
"""

from __future__ import annotations

import argparse
import time

from app.core.config import settings
from app.models.enums import WoodSpecies
from app.services.media.plates import write_plate, write_swatch


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.services.media")
    parser.add_argument("--preview", action="store_true", help="write sample plates")
    parser.add_argument("--count", type=int, default=12)
    args = parser.parse_args()

    if not args.preview:
        parser.print_help()
        return

    root = settings.media_path
    started = time.perf_counter()

    species = list(WoodSpecies)
    for i in range(args.count):
        wood = species[i % len(species)]
        write_plate(
            root, f"_preview/plate_{i:02d}_{wood.value}", wood,
            key=f"preview-{i}", angle=i % 4,
        )
        print(f"  plate {i:02d}  {wood.label}")

    for wood in species:
        write_swatch(root, wood)
    print(f"  {len(species)} swatches")

    elapsed = time.perf_counter() - started
    print(f"\nWrote {args.count} plates in {elapsed:.1f}s -> {root / '_preview'}")
    print(f"Roughly {elapsed / args.count:.2f}s per plate.")


if __name__ == "__main__":
    main()
