import shutil
from pathlib import Path
import argparse

def aggregate_worker_dists(workers_dir, out_dir):
    workers = Path(workers_dir)
    if not workers.is_dir():
        raise ValueError(f"{workers_dir!r} is not a directory")

    dists = Path(out_dir)
    if dists.exists():
        shutil.rmtree(dists)
    dists.mkdir()

    copied_plots = set()

    for wk in sorted(workers.iterdir()):
        if not wk.is_dir():
            continue
        for file in wk.rglob("*"):
            rel = file.relative_to(wk)
            dest = dists / rel
            dest.parent.mkdir(parents=True, exist_ok=True)

            if file.suffix == ".txt" and "data" in file.parts:
                with file.open("r") as fin, dest.open("a") as fout:
                    fout.writelines(fin.readlines())

            elif "plot" in file.parts:
                if rel not in copied_plots:
                    shutil.copy(file, dest)
                    copied_plots.add(rel)

    print(f"Aggregated worker outputs into {dists}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Aggregator CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("aggregate", help="Make dists")
    c.add_argument("--workers-dir", required=True)
    c.add_argument("--out-dir", required=True)

    args = p.parse_args()

    if args.cmd == "aggregator":
        aggregate_worker_dists(args.workers_dir, args.out_dir)