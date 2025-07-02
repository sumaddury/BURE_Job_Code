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

_ansi = re.compile(r'\x1b\[[0-9;]*m')

# _num = re.compile(r'[-+]?(?:\d*\.\d+|\d+)')
_num = re.compile(r'''           
     [-+]?(?:\d*\.\d+|\d+)
     (?:[eE][-+]?\d+)?
''', re.VERBOSE)

def expected_pairs(stdout):
    full = " ".join(_ansi.sub("", line) for line in stdout)

    m_pass = re.search(r'(\d+)\s+passed', full)
    m_fail = re.search(r'(\d+)\s+failed', full)

    passed = int(m_pass.group(1)) if m_pass else 0
    failed = int(m_fail.group(1)) if m_fail else 0

    total = passed + failed
    return total

def parse_output(stdout):
    nums = []
    exp = expected_pairs(stdout)
    if exp == 0:
        warnings.warn("expected_pairs returned 0", UserWarning, stacklevel=2)
    for line in stdout:
        text = _ansi.sub("", line).strip()
        if not text or text == ".":
            continue

        if "FLAKY_METRIC:" in text:
            matches = _num.findall(text)
            if len(matches) != 1:
                raise RuntimeError("Expected exactly one FLAKY_METRIC value", line)
            nums.append(float(matches[0]))
            continue
            
        low = text.lower()
        if any(keyword in low for keyword in ("passed", "failed", "skipped")):
            continue

    if len(nums) % 2 != 0:
        raise RuntimeError("Even number of pairs", nums)
    pairs = [(nums[i], nums[i+1]) for i in range(0, len(nums), 2)]
    if len(pairs) != exp:
        raise RuntimeError(f"Expected {exp} pairs, but parsed {len(pairs)}", nums)

    return pairs

def plot_distribution(data, bins=20, title='Distribution', xlabel='Value', ylabel='Frequency', expected=None):
    fig, ax = plt.subplots()
    ax.hist(data, bins=bins, edgecolor='black', alpha=0.75)
    if expected is not None:
        ax.axvline(expected, color='red', linestyle='--', linewidth=2, label=f'Expected = {expected}', zorder=5)
        ax.legend()
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    return fig, ax

def do_trial(test_input, safeguard=2):
    err = None
    for _ in range(safeguard):
        try:
            warnings.simplefilter("always")
            pkg = run_pytest(
                LOGGED_PATH   = test_input["LOGGED_PATH"],
                CLASS         = test_input["CLASS"],
                TEST          = test_input["TEST"],
                repo_name     = test_input["repo_name"],
                seed_value    = test_input["seed_value"],
                seed_config_name = test_input["seed_config_name"],
                seed_config_file = test_input["seed_config_file"],
            )
            with warnings.catch_warnings(record=True) as caught:
                pairs = parse_output(pkg["stdout"])
            for w in caught:
                if issubclass(w.category, UserWarning) and "expected_pairs returned 0" in str(w.message):
                    raise RuntimeError("No data is being recorded", pkg)

            if pkg["returncode"] != 0 and not pairs:
                raise RuntimeError("Runtime test failure", pkg)
            return pairs
        except Exception as e:
            err = e
    raise RuntimeError("All safeguards failed.", err)


def sample_test(test_input, foldername=None, trials=100, max_workers=4, show_plot=False, save_plot=False):
    max_workers = max_workers or os.cpu_count()
    values = None
    expected = None
    
    print(f"Sampling {test_input['TEST']}...")
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(do_trial, test_input) for _ in range(trials)]
        for r, future in enumerate(as_completed(futures), start=1):
            try:
                pairs = future.result()
            except RuntimeError as e:
                raise RuntimeError(f"Trial {r} failed", e)

            if values is None:
                values   = [[] for _ in range(len(pairs))]
            if expected is None:
                expected = [pair[1] for pair in pairs]
            for i, pair in enumerate(pairs):
                values[i].append(pair[0])
            print(r, end=", ", flush=True)

    if len(values) != len(expected):
        raise RuntimeError("Sanity check failed.", values, expected)
    for i, parametrization in enumerate(values):
        figure = plot_distribution(parametrization, title=str(i), expected=expected[i])
        if show_plot:
            figure[0].show()
        if foldername:
            temp = f"_{expected[i]}_{i}"
            if save_plot:
                plot_path = Path(foldername) / "plot"
                plot_path.mkdir(parents=True, exist_ok=True)
                figure[0].savefig(plot_path / f"{temp}.png")
            data_path = Path(foldername) / "data"
            data_path.mkdir(parents=True, exist_ok=True)
            with open(data_path / f"{temp}.txt", 'w') as f:
                for x in parametrization:
                    f.write(f"{x:.10f}\n")
    return (values, expected)

def test_line(tup, out_name, repo_name, seed_value, seed_config_file, seed_config_names, trials=100, max_workers=4):
    test_input = {'LOGGED_PATH' : tup.logged_path, 'CLASS' : tup.testclass, 'TEST' : tup.testname, 'repo_name' : repo_name, 
                  'seed_value' : seed_value, 'seed_config_file' : seed_config_file}
    path = out_name + "/" + tup.testname + "_" + str(tup.line_number) + "/"
    output = {}
    for seed_config_name in seed_config_names:
        print(f"\nConfig {seed_config_name}")
        test_input['seed_config_name'] = seed_config_name
        temp = path + "SEEDS_" + seed_config_name.replace(", ", "_")
        try:
            pack = sample_test(test_input, foldername=temp, trials=trials, max_workers=max_workers, show_plot=False, save_plot=True)
        except RuntimeError as e:
            raise RuntimeError("Config failed", seed_config_name, e)
        output[seed_config_name] = pack
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

    def assertion_id(tup):
        return f"{tup.testname}_{tup.line_number}"

    if args.cmd == "sample_csv":
        t1 = time.time() / 60.0
        seed_configs = [s.strip() for s in args.seed_config_names.split(';') if s.strip()]
        tests = read_csv(args.csv_in, keep_default_na=False)
        if args.assertions:
            ASSERTIONS = set(s.strip() for s in args.assertions.split(",") if s.strip())
            test_tups = [(idx, tup) for idx, tup in enumerate(tests.itertuples()) if assertion_id(tup) in ASSERTIONS]
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