import subprocess
from pathlib import Path
import ast
import csv
import itertools
import sys
import argparse
import pickle

class AssertionMiner(ast.NodeVisitor):
    def __init__(self, filepath: str, source_text: str):
        self.filepath = filepath
        self.source_text = source_text
        self.current_class = ""
        self.current_function = ""
        self.rows = []
        self.function_defs = {}

    def visit_ClassDef(self, node: ast.ClassDef):
        prev_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = prev_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.function_defs[self.current_class + "." + node.name] = node
        prev_function = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = prev_function
    
    def visit_Assert(self, node: ast.Assert):
        test = node.test
        if isinstance(test, ast.Compare) and len(test.ops) == 1 and len(test.comparators) == 1:
            op = test.ops[0]
            if isinstance(op, (ast.Lt, ast.Gt, ast.LtE, ast.GtE)):
                rhs = test.comparators[0]
                if isinstance(rhs, ast.Constant):
                    snippet = ast.get_source_segment(self.source_text, node)
                    assertion_type = "Python assert (<,>,<=,>= threshold)"
                    self.rows.append((self.filepath, self.current_class, self.current_function, assertion_type,node.lineno,snippet))
        self.generic_visit(node)
    
    def visit_Call(self, node: ast.Call):
        name = node.func.id if isinstance(node.func, ast.Name) else (node.func.attr if isinstance(node.func, ast.Attribute) else None)
        snippet = None

        UNITTEST_METHODS = {
            # "assertTrue", "assertFalse",
            "assertGreater", "assertGreaterEqual",
            "assertLess", "assertLessEqual"
        }
        if name in UNITTEST_METHODS:
            snippet = ast.get_source_segment(self.source_text, node)
            assertion_type = f"unittest.{name}"
            self.rows.append((self.filepath, self.current_class, self.current_function, assertion_type,node.lineno,snippet))
        
        if name == "approx":
            snippet = ast.get_source_segment(self.source_text, node)
            assertion_type = "pytest.approx"
            self.rows.append((self.filepath, self.current_class, self.current_function, assertion_type,node.lineno,snippet))

        NUMPY_TESTING_METHODS = {
            "assert_almost_equal",
            "assert_approx_equal",
            "assert_array_almost_equal",
            "assert_allclose",
            "assert_array_less"
        }
        if name in NUMPY_TESTING_METHODS:
            func_attr = node.func
            if isinstance(func_attr, ast.Attribute):
                parent = func_attr.value
                if isinstance(parent, ast.Attribute) and parent.attr == "testing":
                    snippet = ast.get_source_segment(self.source_text, node)
                    assertion_type = f"numpy.{name}"
                    self.rows.append((self.filepath, self.current_class, self.current_function, assertion_type,node.lineno,snippet))

        if name == "assertAllClose":
            func_attr = node.func
            if isinstance(func_attr, ast.Attribute):
                parent = func_attr.value
                if isinstance(parent, ast.Name) and parent.id == "tf":
                    snippet = ast.get_source_segment(self.source_text, node)
                    assertion_type = "tensorflow.assertAllClose"
                    self.rows.append((self.filepath, self.current_class, self.current_function, assertion_type,node.lineno,snippet))
        self.generic_visit(node)

def compile_project(LINK, TARGET, ):
    if Path(TARGET).exists():
        raise FileExistsError(f"'{TARGET}' already exists.")
    cmd = ['git','clone',LINK,TARGET]
    subprocess.run(cmd, check=True, text=True)
    py_trees = {}
    root = Path(TARGET)
    for path in root.rglob('*'):
        if path.is_file() and path.suffix == ".py":
            py_trees[str(path)] = ast.parse(path.read_text(),filename=str(path))
    return py_trees

def mine_file(PATH: str, TREE: ast.Module):
    source_text = open(PATH).read()
    finder = AssertionMiner(PATH, source_text)
    finder.visit(TREE)
    return finder.rows, finder.function_defs

def mine_project(ast_dict, CSV_TARGET):
    mines = [mine_file(path, ast_dict[path]) for path in ast_dict]
    rows = [e[0] for e in mines]
    funcs = {}
    for i, path in enumerate(ast_dict):
        funcs[path] = mines[i][1]
    flat_rows = list(itertools.chain.from_iterable(rows))
    with open(CSV_TARGET, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["filepath", "testclass", "testname", "assertion_type", "line_number", "assert_string"])
        writer.writerows(flat_rows)
    return funcs

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="AssertSpecFinder CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("compile", help="Clone project and build ASTs")
    c.add_argument("--project-link", required=True)
    c.add_argument("--clone-dir", required=True)
    c.add_argument("--asts-out", required=True)

    m = sub.add_parser("mine", help="Mine assertions from ASTs")
    m.add_argument("--asts-in", required=True)
    m.add_argument("--csv-target", required=True)
    m.add_argument("--funcs-out", required=True)

    args = p.parse_args()

    if args.cmd == "compile":
        asts = compile_project(args.project_link, args.clone_dir)
        with open(args.asts_out, "wb") as f: pickle.dump(asts, f)
        print(f"ASTs → {args.asts_out}, project → {args.clone_dir}")

    elif args.cmd == "mine":
        with open(args.asts_in, "rb") as f: asts = pickle.load(f)
        funcs = mine_project(asts, args.csv_target)
        with open(args.funcs_out, "wb") as f: pickle.dump(funcs, f)
        print(f"Assertions CSV → {args.csv_target}, Funcs → {args.funcs_out}")

    
