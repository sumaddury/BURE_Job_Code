import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import skew, kurtosis

def compile_param_stats(root_dir, save_csv = None) -> pd.DataFrame:
    root = Path(root_dir).expanduser().resolve()
    rows = []

    for txt_path in root.rglob("*.txt"):
        rel_parts = txt_path.relative_to(root).parts
        if len(rel_parts) < 3:
            continue
        test_name, seed_cfg = rel_parts[0], rel_parts[1]

        stem_parts = txt_path.stem.split(".")
        if len(stem_parts) < 2:
            continue
        expected_val, param_idx = stem_parts[0], stem_parts[-1]
        param_tag = f"{expected_val}-p{param_idx}"

        data = np.loadtxt(txt_path, dtype=float)
        if data.size == 0:
            continue

        n       = data.size
        mean    = data.mean()
        var     = data.var(ddof=0)
        q25, q75 = np.percentile(data, [25, 75])
        data_skew     = skew(data)
        data_kurtosis = kurtosis(data, fisher=True, bias=False)

        rows.append(
            dict(
                test_name=test_name,
                seed_cfg=seed_cfg,
                param_tag=param_tag,
                expected=float(expected_val[1:]),
                n=n,
                mean=mean,
                var=var,
                q25=q25,
                q75=q75,
                min=data.min(),
                max=data.max(),
                skew=data_skew,
                kurtosis=data_kurtosis,
                path_txt=str(txt_path),
                path_png=str(txt_path.with_suffix(".png")),
            )
        )

    df = pd.DataFrame(rows)

    dup_mask = df.duplicated(subset=["test_name", "seed_cfg", "param_tag"])
    if dup_mask.any():
        raise ValueError(
            "Duplicate parametrization tags detected:\n"
            f"{df[dup_mask][['test_name','seed_cfg','param_tag']].head()}"
        )

    numeric_cols = ["mean", "var"]
    if df[numeric_cols].isna().any().any():
        raise ValueError("NaNs found in computed statistics – verify input files.")

    if save_csv:
        out_path = save_csv
        df.to_csv(out_path, index=False)
        print(f"Saved: {out_path}")

    return df

def slice_by_param(df, param, constraint) -> pd.DataFrame:
    sub = df.loc[df[param] == constraint].copy().reset_index(drop=True)

    return sub

def extract_row(df, unique_col, key):
    mask = df[unique_col] == key
    match = df.loc[mask]

    if len(match) == 0:
        raise KeyError(f"Value {key!r} not found in column {unique_col!r}.")
    if len(match) > 1:
        raise ValueError(
            f"Multiple rows found for value {key!r} in column {unique_col!r}; "
            "column is not unique as assumed."
        )

    row_tuple = next(match.itertuples(index=True))
    return row_tuple