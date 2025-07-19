import argparse
import shutil
import sys
from pathlib import Path

def merge_txt_files(src_paths, dest_path, verbose=False):
    if verbose:
        print(f"  → Merging {len(src_paths)} files into {dest_path}")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with dest_path.open('w') as fout:
        for p in src_paths:
            if not p.exists():
                print(f"    ! WARNING: {p} does not exist", file=sys.stderr)
                continue
            if verbose:
                print(f"    • reading {p}")
            with p.open('r') as fin:
                for line in fin:
                    fout.write(line)

def main(workers_dir: Path, out_dir: Path, verbose=False):
    # 0) discover worker dirs
    workers = sorted(d for d in workers_dir.iterdir() if d.is_dir())
    print(f"Found {len(workers)} workers: {[w.name for w in workers]}")
    if not workers:
        print(f"ERROR: no subdirectories in {workers_dir}", file=sys.stderr)
        sys.exit(1)
    template = workers[0]

    # 1) find tests present in every worker
    tests_per_worker = [
        {p.name for p in w.iterdir() if p.is_dir()}
        for w in workers
    ]
    common_tests = set.intersection(*tests_per_worker)

    # 2) filter to tests where each worker has exactly 3 seeds, same names
    tests_and_seeds = {}
    for test in sorted(common_tests):
        seed_sets = []
        for w in workers:
            test_dir = w / test
            if not test_dir.is_dir():
                seed_sets = []
                break
            seeds = {p.name for p in test_dir.iterdir() if p.is_dir()}
            if len(seeds) != 3:
                seed_sets = []
                break
            seed_sets.append(seeds)
        if not seed_sets:
            if verbose:
                print(f"Skipping test '{test}': missing or wrong number of seed configs")
            continue
        # all seed-sets must be identical
        if not all(seeds == seed_sets[0] for seeds in seed_sets):
            if verbose:
                print(f"Skipping test '{test}': seed-config names differ across workers")
            continue
        tests_and_seeds[test] = sorted(seed_sets[0])

    if not tests_and_seeds:
        print("ERROR: no tests with all 3 seed-configs present; nothing to merge", file=sys.stderr)
        sys.exit(1)

    print(f"Will merge these tests: {list(tests_and_seeds.keys())}")

    # 3) copy non-data, non-plot files/folders from template (only for kept tests)
    print("\nCopying non-data files/folders:")
    for src in template.rglob('*'):
        # skip any data or plots content
        if 'data' in src.parts or 'plots' in src.parts:
            continue
        rel = src.relative_to(template)
        # if this is under a test that we're not including, skip it
        if rel.parts and rel.parts[0] in common_tests and rel.parts[0] not in tests_and_seeds:
            continue
        dest = out_dir / rel
        if src.is_dir():
            if verbose:
                print(f"  • mkdir {dest}")
            dest.mkdir(parents=True, exist_ok=True)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if verbose:
                print(f"  • copy {src} → {dest}")
            shutil.copy2(src, dest)

    # 4) aggregate only the common tests & seeds, matching parametrizations by index
    print("\nAggregating .txt data files and one plot per parametrization:")
    for test, seeds in tests_and_seeds.items():
        for seed in seeds:
            data_dir = template / test / seed / 'data'
            plot_dir = template / test / seed / 'plots'
            if not data_dir.is_dir():
                if verbose:
                    print(f"  • skipping missing data dir {data_dir}")
                continue

            # collect all parametrization indices from the template data folder
            indices = [p.stem.split('_')[-1] for p in data_dir.glob('*.txt')]

            for idx in indices:
                # 4a) gather the .txt files for this index from every worker
                src_txts = []
                for w in workers:
                    dd = w / test / seed / 'data'
                    matches = [p for p in dd.glob('*.txt') if p.stem.split('_')[-1] == idx]
                    if len(matches) == 1:
                        src_txts.append(matches[0])
                    else:
                        if verbose:
                            print(f"    ! skipping {test}/{seed} idx={idx}: found {len(matches)} matches in {dd}")
                        src_txts = []
                        break
                if not src_txts:
                    continue

                # use the template filename for the output path
                template_file = next(p for p in data_dir.glob('*.txt') if p.stem.split('_')[-1] == idx)
                rel_txt = template_file.relative_to(template)
                merge_txt_files(src_txts, out_dir / rel_txt, verbose=verbose)

                # 4b) copy the first plot for this index from the template
                if plot_dir.is_dir():
                    plot_file = next((p for p in plot_dir.iterdir() if p.stem.split('_')[-1] == idx), None)
                    if plot_file:
                        rel_plot = plot_file.relative_to(template)
                        dest_plot = out_dir / rel_plot
                        dest_plot.parent.mkdir(parents=True, exist_ok=True)
                        if verbose:
                            print(f"    • copy plot {plot_file} → {dest_plot}")
                        shutil.copy2(plot_file, dest_plot)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Merge worker_* result dirs into one, aggregating data/*.txt"
    )
    parser.add_argument('-w', '--workers-dir', required=True, type=Path,
                        help="parent dir containing worker subdirs (e.g. '0','1',...)")
    parser.add_argument('-o', '--out-dir', required=True, type=Path,
                        help="directory to write merged output")
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="print each file/folder as it’s processed")
    args = parser.parse_args()
    main(args.workers_dir, args.out_dir, verbose=args.verbose)
