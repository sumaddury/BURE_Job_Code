import pytest
import importlib
import yaml
from collections import defaultdict

def pytest_addoption(parser):
    parser.addoption("--seed-config-file",  default="seed_configs.yaml")
    parser.addoption("--seed-config-name",  default="minimal")
    parser.addoption("--seed-value",        type=int, default=0)

def rec_getattr(obj, attr_path, default=None):
    current = obj
    for part in attr_path.split("."):
        current = getattr(current, part, None)
        if current is None:
            return default
    return current

@pytest.fixture(autouse=True)
def apply_seed_config(request):
    cfg_file = request.config.getoption("seed_config_file")
    cfg_name = request.config.getoption("seed_config_name")
    seed_val = request.config.getoption("seed_value")

    with open(cfg_file) as f:
        all_cfgs = yaml.safe_load(f)
    try:
        subconfigs = [s.strip() for s in cfg_name.split(",") if s.strip()]
        fqn_list = [fqn for subconfig in subconfigs for fqn in all_cfgs[subconfig]]
    except KeyError:
        raise pytest.UsageError(f"Unknown seed config {cfg_name!r}")
    
    if not fqn_list:
        return

    groups = defaultdict(list)
    for fqn in fqn_list:
        module, _, func = fqn.partition(".")
        groups[module].append(func)

    seed_callables = []
    for module, funcs in groups.items():
        try:
            pkg = importlib.import_module(module)
        except ImportError:
            raise pytest.UsageError(f"In seed‐config {cfg_name!r}, could not import {module!r}")

        found_any = False
        for name in funcs:
            fn = rec_getattr(pkg, name, None)
            if callable(fn):
                seed_callables.append(fn)
                found_any = True
        if not found_any:
            raise pytest.UsageError(f"In seed‐config {cfg_name!r}, none of {funcs} found in module {module!r}")

    for fn in seed_callables:
        try:
            fn(seed_val)
        except:
            fn()

