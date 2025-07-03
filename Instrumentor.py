import ast
import copy
from typing import cast
from pathlib import Path
import argparse
from pandas import read_csv
import pickle

class Logger(ast.NodeTransformer):
    def __init__(self, target_lineno: int):
        super().__init__()
        self.target_lineno = target_lineno

    def visit_Assert(self, node: ast.Assert):
        if node.lineno != self.target_lineno:
            return node
        node = cast(ast.Assert, self.generic_visit(node))

        if (isinstance(node.test, ast.Compare) and len(node.test.ops) == 1 and isinstance(node.test.ops[0], ast.Eq) and isinstance(node.test.comparators[0], ast.Call)):
            lhs       = node.test.left
            rhs_call  = node.test.comparators[0]
            func      = rhs_call.func
            is_approx = (
                (isinstance(func, ast.Name)      and func.id  == "approx") or
                (isinstance(func, ast.Attribute) and func.attr == "approx")
            )

            if is_approx and rhs_call.args:
                lhs_copy = copy.deepcopy(lhs)
                fstr_left = ast.JoinedStr([
                    ast.Constant("\nFLAKY_METRIC: "),
                    ast.FormattedValue(
                        value=ast.Call(ast.Name("float", ast.Load()),
                                    [lhs_copy], []),
                        conversion=-1, format_spec=None)
                ])
                print_left = ast.Expr(
                    ast.Call(ast.Name("print", ast.Load()), [fstr_left], []))

                ref_copy = copy.deepcopy(rhs_call.args[0])
                fstr_ref = ast.JoinedStr([
                    ast.Constant("\nFLAKY_METRIC: "),
                    ast.FormattedValue(
                        value=ast.Call(ast.Name("float", ast.Load()),
                                    [ref_copy], []),
                        conversion=-1, format_spec=None)
                ])
                print_ref = ast.Expr(
                    ast.Call(ast.Name("print", ast.Load()), [fstr_ref], []))

                return [print_left, print_ref, node]
        if isinstance(node.test, ast.Compare):
            left = copy.deepcopy(node.test.left)
            right = copy.deepcopy(node.test.comparators[0])
            fstr_left = ast.JoinedStr([ast.Constant("\nFLAKY_METRIC: "), ast.FormattedValue(value=ast.Call(
                        func=ast.Name(id="float", ctx=ast.Load()),
                        args=[ left ],
                        keywords=[]), 
                        conversion=-1, format_spec=None)])
            print_left = ast.Expr(ast.Call(
                func=ast.Name(id="print", ctx=ast.Load()),
                args=[fstr_left],
                keywords=[]))
            fstr_right = ast.JoinedStr([ast.Constant("\nFLAKY_METRIC: "), ast.FormattedValue(value=ast.Call(
                        func=ast.Name(id="float", ctx=ast.Load()),
                        args=[ right ],
                        keywords=[]),
                    conversion=-1, format_spec=None)])
            print_right = ast.Expr(ast.Call(
                func=ast.Name(id="print", ctx=ast.Load()),
                args=[fstr_right],
                keywords=[]))
            return [print_left, print_right, node]
        else:
            return node
    
    def visit_Expr(self, node: ast.Expr):
        if node.lineno != self.target_lineno:
            return self.generic_visit(node)

        node = cast(ast.Expr, self.generic_visit(node))
        if isinstance(node.value, ast.Call):
            
            call = cast(ast.Call, node.value)

            left, right = None, None
            if len(call.args) >= 2:
                left = call.args[0]
                right = call.args[1]
            elif len(call.args) == 1:
                left = call.args[0]
                for kw in call.keywords:  
                    if kw.arg in {"second", "desired", "y", "b", "expected"}:  
                        right = kw.value  
            else:
                for kw in call.keywords:  
                    if kw.arg in {"first", "actual", "x", "a"}:  
                        left = kw.value  
                    elif kw.arg in {"second", "desired", "y", "b"}:  
                        right = kw.value  
            if left and right:
                left_copy = copy.deepcopy(left)
                right_copy = copy.deepcopy(right)
                fstr_left = ast.JoinedStr([ast.Constant("\nFLAKY_METRIC: "), ast.FormattedValue(value=ast.Call(
                            func=ast.Name(id="float", ctx=ast.Load()),
                            args=[ left_copy ],
                            keywords=[]), 
                            conversion=-1, format_spec=None)])
                print_left = ast.Expr(ast.Call(
                    func=ast.Name(id="print", ctx=ast.Load()),
                    args=[fstr_left],
                    keywords=[]))
                fstr_right = ast.JoinedStr([ast.Constant("\nFLAKY_METRIC: "), ast.FormattedValue(value=ast.Call(
                            func=ast.Name(id="float", ctx=ast.Load()),
                            args=[ right_copy ],
                            keywords=[]),
                        conversion=-1, format_spec=None)])
                print_right = ast.Expr(ast.Call(
                    func=ast.Name(id="print", ctx=ast.Load()),
                    args=[fstr_right],
                    keywords=[]))
                return [print_left, print_right, node]
        return node
    
def log_assertion(PATH, CLS, TST, AST_DICT, FUNCS_DICT, LINE_NO):
    logged_tree = copy.deepcopy(AST_DICT[PATH])
    func_node = copy.deepcopy(FUNCS_DICT[PATH][CLS + "." + TST])
    logger = Logger(LINE_NO)
    logged_func_node = logger.visit(func_node)

    if CLS:
        for cls_node in logged_tree.body:
            if isinstance(cls_node, ast.ClassDef) and cls_node.name == CLS:
                for i, member in enumerate(cls_node.body):
                    if (isinstance(member, ast.FunctionDef) and member.name == TST and cls_node.name == CLS):
                        cls_node.body[i] = logged_func_node
                        break
                break

    else:
        for i, member in enumerate(logged_tree.body):
            if isinstance(member, ast.FunctionDef) and member.name == TST:
                logged_tree.body[i] = logged_func_node
                break
            
    ast.fix_missing_locations(logged_tree)
    logged_code = ast.unparse(logged_tree)
    orig = Path(PATH)
    Path(orig.with_name(f"{orig.stem}_{LINE_NO}{orig.suffix}")).write_text(logged_code)
    return logged_tree, logged_func_node

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Instrumentor CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("log", help="Add print statements to assertions")
    c.add_argument("--csv-in", required=True)
    c.add_argument("--csv-out", required=True)
    c.add_argument("--asts-in", required=True)
    c.add_argument("--funcs-in", required=True)

    args = p.parse_args()

    tests = read_csv(args.csv_in, keep_default_na=False)
    tests['logged_path'] = ''

    with open(args.asts_in, "rb") as f: asts = pickle.load(f)
    with open(args.funcs_in, "rb") as f: funcs = pickle.load(f)

    if args.cmd == "log":
        for idx, test in enumerate(tests.itertuples()):
            print(f"{idx}: Processing {test}")
            try:
                log_assertion(PATH=str(test.filepath),
                            CLS=str(test.testclass),
                            TST=str(test.testname),
                            AST_DICT=asts,
                            FUNCS_DICT=funcs,
                            LINE_NO=int(str(test.line_number)) )
                out_path = str(test.filepath)[:-3] + "_" + str(test.line_number) + ".py"
                tests.loc[idx, 'logged_path'] = out_path
                print(f"Logged version → {out_path}")
            except Exception as e:
                print(f"Error with: {e}")
        
        tests.to_csv(args.csv_out, index=False)

    


