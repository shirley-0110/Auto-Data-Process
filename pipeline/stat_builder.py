
import pandas as pd
import os



def find_sas_folder(base):
    """
    自動找到真正放 .sas7bdat 的資料夾
    """
    for root, dirs, files in os.walk(base):
        if any(f.endswith(".sas7bdat") for f in files):
            return root
    return base


def load_cube(path):
    datasets = {}

    for f in os.listdir(path):
        if f.endswith(".sas7bdat"):
            full = os.path.join(path, f)
            df = pd.read_sas(full)
            datasets[f.split(".")[0]] = df

    return datasets


def map_visit(fmt):
    if fmt is None:
        return None
    fmt = str(fmt).lower()

    if "unscheduled" in fmt or "all visit" in fmt:
        return "UN"
    if "screen" in fmt:
        return "S"
    if "cycle 1 day 1" in fmt or "c1d1" in fmt:
        return "C1D1"

    return None


def run_pipeline(cube_path, schema_path):

    cube_path = find_sas_folder(cube_path)
    data = load_cube(cube_path)

    outputs = {}

    summary = []

    for name, df in data.items():

        df = df.copy()
        df["FORM"] = name.upper()

        if "VISIT_FMT" in df.columns:
            df["VISIT_STD"] = df["VISIT_FMT"].apply(map_visit)
        else:
            df["VISIT_STD"] = None

        mapped = df["VISIT_STD"].notna().sum()

        summary.append({
            "dataset": name,
            "total": len(df),
            "mapped": int(mapped),
            "unmapped": int(len(df) - mapped)
        })

        outputs[name] = df

    qc = pd.DataFrame(summary)

    return outputs, qc

