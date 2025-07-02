import ast
import argparse
import pickle

RANDOM_SEEDS = {"random.seed"}
NUMPY_SEEDS = {"numpy.random.seed", "numpy.random.set_state", "numpy.random.default_rng",
               "numpy.random.RandomState.seed", "numpy.random.RandomState.set_state"}
TORCH_SEEDS = {"torch.seed", "torch.manual_seed", "torch.set_rng_state", 
               "torch.use_deterministic_algorithms", 
               "torch.cuda.set_rng_state", "torch.cuda.set_rng_state_all", 
               "torch.cuda.seed", "torch.cuda.seed_all", 
               "torch.cuda.manual_seed", "torch.cuda.manual_seed_all"}
TENSORFLOW_SEEDS = {"tensorflow.random.set_seed", "tensorflow.compat.v1.set_random_seed", "tensorflow.keras.utils.set_random_seed"}

def resolve_func(call_node):
    parts = []
    obj = call_node.func

    while isinstance(obj, ast.Attribute):
        parts.append(obj.attr)
        obj = obj.value
    if isinstance(obj, ast.Name):
        parts.append(obj.id)
    
    if not parts:
        return ""
    parts.reverse()

    if parts[0] in ALIAS_MAP:
        parts[0] = ALIAS_MAP[parts[0]]

    return ".".join(parts)

def update_alias(import_node):
    if isinstance(import_node, ast.Import):
        for alias in import_node.names:
            local = alias.asname or alias.name.split('.')[0]
            ALIAS_MAP[local] = alias.name

    elif isinstance(import_node, ast.ImportFrom):
        module = import_node.module or ""
        for alias in import_node.names:
            local = alias.asname or alias.name
            full = f"{module}.{alias.name}" if module else alias.name
            ALIAS_MAP[local] = full

def get_seed_lines(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            update_alias(node)

    seed_lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fqn = resolve_func(node)
            if any(fqn.startswith(seed) for seed in ALL_SEED_APIS):
                seed_lines.append(node.lineno)
    
    return seed_lines

def unseed(seed_lines, path):
    with open(path, "r", encoding="utf-8") as f:
        source_lines = f.readlines()

    new_lines = []
    for idx, line in enumerate(source_lines, start=1):
        if idx in seed_lines and not line.lstrip().startswith("#"):
            indent = line[: len(line) - len(line.lstrip())]
            commented = line.rstrip("\n")
            new_line = f"{indent}pass  # {commented}\n"
            new_lines.append(new_line)
        else:
            new_lines.append(line)

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    return new_lines

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Seeder CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("remove_seed", help="Commend seeding lines")
    c.add_argument("--asts-in", required=True)
    for name, default in [
        ("random-seeds",     RANDOM_SEEDS),
        ("numpy-seeds",      NUMPY_SEEDS),
        ("torch-seeds",      TORCH_SEEDS),
        ("tensorflow-seeds", TENSORFLOW_SEEDS),
    ]:
        c.add_argument(f"--{name}",
            type=lambda s: set(item.strip() for item in s.split(",") if item.strip()), 
            required=False, 
            default=default,
            help=f"Comma-separated list for {name}")
    c.add_argument("--all-seeds",
        type=lambda s: set(item.strip() for item in s.split(",") if item.strip()), 
        required=False,
        default=None,
        help="If set, overrides the specific --*-seeds lists")
    
    args = p.parse_args()

    if args.all_seeds is not None:
        ALL_SEED_APIS = args.all_seeds
    else:
        ALL_SEED_APIS = args.random_seeds | args.numpy_seeds | args.torch_seeds | args.tensorflow_seeds
    print(f"Using seeds: {','.join(sorted(ALL_SEED_APIS))}...")

    with open(args.asts_in, "rb") as f: asts = pickle.load(f)
    
    if args.cmd == "remove_seed":
        print(f"Analyzing {len(asts.items())} python files...")
        for (path, tree) in asts.items():
            print(f"Processing {path}... ", end='')
            ALIAS_MAP = {}
            hits = get_seed_lines(tree)
            unseed(hits, path)
            print(f"Found {len(hits)} seed lines in {path}")
            

    



