import matplotlib.pyplot as plt
import sys
from Sampler import run_pytest
import re
import argparse
from pathlib import Path
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
import os
from pandas import read_csv
import time

def do_trial(test_input):
    pkg = run_pytest(
        LOGGED_PATH        = test_input["PATH"],
        CLASS              = test_input["CLASS"],
        TEST               = test_input["TEST"],
        repo_name          = test_input["repo_name"],
        seed_value         = test_input.get("seed_value"),
        seed_config_name   = test_input.get("seed_config_name"),
        seed_config_file   = test_input.get("seed_config_file"),
    )
    if pkg["returncode"] in {0, 1}:
        return int(pkg["returncode"])
    else:
        raise RuntimeError(f"pytest exited with unexpected code {pkg['returncode']}", pkg)

def sample_test(test_input,
                foldername=None,
                trials=100,
                max_workers=4):
    max_workers = max_workers or os.cpu_count()
    results = []

    print(f"Sampling {test_input['TEST']}…")
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(do_trial, test_input)
                   for _ in range(trials)]
        for i, future in enumerate(as_completed(futures), start=1):
            passed = future.result()

            results.append(passed)
            print(i, end=", ", flush=True)
    print()

    if foldername:
        data_dir = Path(foldername) / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        with open(data_dir / "results.txt", "w") as f:
            for ok in results:
                f.write(f"{int(ok)}\n")

    return results

def test_line(tup, out_name, repo_name, seed_value, seed_config_file, seed_config_names, trials=100, max_workers=4):
    test_input = {
        'PATH'              : tup.filepath,
        'CLASS'             : tup.testclass,
        'TEST'              : tup.testname,
        'repo_name'         : repo_name,
        'seed_value'        : seed_value,
        'seed_config_file'  : seed_config_file
    }
    path = out_name + "/" + tup.testname + "_" + str(tup.line_number) + "/"
    output = {}
    for cfg in seed_config_names:
        print(f"\nConfig {cfg}")
        test_input['seed_config_name'] = cfg
        temp = path + "SEEDS_" + cfg.replace(", ", "_")
        results = sample_test(test_input,
                              foldername=temp,
                              trials=trials,
                              max_workers=max_workers)
        output[cfg] = results
    return output

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Distributions CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("sample_csv", help="Test a csv of logged assertions")
    c.add_argument("--csv-in", required=True)
    c.add_argument("--assertions", default=None, required=False)
    c.add_argument("--trials", default=100, type=int, required=False)
    c.add_argument("--workers", default=4, type=int, required=False)
    c.add_argument("--dir-out", required=True)
    c.add_argument("--repo-name", required=True)
    c.add_argument("--seed-value", required=True)
    c.add_argument("--seed-config-file-in", required=True)
    c.add_argument("--seed-config-names", required=True)
    
    args = p.parse_args()

    if args.cmd == "sample_csv":
        t1 = time.time() / 60.0
        seed_configs = [s.strip() for s in args.seed_config_names.split(';') if s.strip()]
        tests = read_csv(args.csv_in, keep_default_na=False)
        if args.assertions:
            ASSERTIONS = set(s.strip() for s in args.assertions.split(",") if s.strip())
            test_tups = [(idx, tup) for idx, tup in enumerate(tests.itertuples()) if tup.testname in ASSERTIONS]
        else:
            test_tups = list(enumerate(tests.itertuples()))
        for t in test_tups:
            if not "test" in t[1].testname:
                continue
            print(f"\n|{t[0]}:{round((time.time() / 60.0) - t1, 2)}|__________Trying {t[1]}____________________")
            try:
                test_line(t[1], args.dir_out, args.repo_name, args.seed_value, args.seed_config_file_in, seed_configs, 
                          int(args.trials), int(args.workers))
            except Exception as e:
                print(f"Skipping {t[0]}", str(e))