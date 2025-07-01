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
    workers = sorted([d for d in workers_dir.iterdir() if d.is_dir()])
    print(f"Found {len(workers)} workers: {[w.name for w in workers]}")
    if not workers:
        print(f"ERROR: no subdirectories in {workers_dir}", file=sys.stderr)
        sys.exit(1)
    template = workers[0]

    print("\nCopying non-data files/folders:")
    for src in template.rglob('*'):
        if 'data' in src.parts:
            continue
        rel = src.relative_to(template)
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

    print("\nAggregating .txt data files:")
    for txt in template.rglob('data/*.txt'):
        rel = txt.relative_to(template)
        src_paths = [w / rel for w in workers]
        dest_txt = out_dir / rel
        merge_txt_files(src_paths, dest_txt, verbose=verbose)

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
