
import pandas as pd
import os


# 自動找到真正放 .sas7bdat 的資料夾
def find_sas_folder(base):
    for root, dirs, files in os.walk(base):
        if any(f.endswith(".sas7bdat") for f in files):
            return root
    return base
    # End ==================================================================

# Load
def load_data(path):
    datasets = {}

    for f in os.listdir(path):
        if f.endswith(".sas7bdat"):
            full = os.path.join(path, f)
            df = pd.read_sas(full)
            datasets[f.split(".")[0]] = df

    return datasets



# 建立 RAW LIST
def build_raw_list(cube_path):

    cube_path = find_sas_folder(cube_path)

    records = []

    for f in os.listdir(cube_path):

        if not f.lower().endswith(".sas7bdat"):
            continue

        dataset = f.split(".")[0].upper()
        full_path = os.path.join(cube_path, f)

        df = pd.read_sas(full_path, format="sas7bdat")

        for col in df.columns:

            dtype = str(df[col].dtype)

            # normalize raw datatype
            if "int" in dtype or "float" in dtype:
                dtype_std = "NUMERIC"
            elif "datetime" in dtype:
                dtype_std = "DATETIME"
            else:
                dtype_std = "TEXT"

            records.append({
                "SOURCE": "RAW",
                "DATASET": dataset,
                "VARIABLE": col.upper(),
                "RAW_DATATYPE": dtype,
                "RAW_DATATYPE_STD": dtype_std
            })

    return pd.DataFrame(records)



# =========================================================
# 3. 建立 SCHEMA LIST（簡化版）
# =========================================================
def build_schema_list(schema_path):

    # 👉 假設每個sheet = dataset
    xls = pd.ExcelFile(schema_path)

    records = []

    for sheet in xls.sheet_names:

        df = pd.read_excel(xls, sheet_name=sheet)

        for col in df.columns:

            # 你可以再改成讀 specific 欄位（之後升級）
            datatype = "TEXT"  # 先簡化（因為你現在 schema 未結構化）

            records.append({
                "SOURCE": "SCHEMA",
                "DATASET": sheet.upper(),
                "VARIABLE": str(col).upper(),
                "SCHEMA_DATATYPE": datatype,
                "SCHEMA_DATATYPE_STD": datatype
            })

    return pd.DataFrame(records)


# =========================================================
# 4. 比較 Schema vs Raw
# =========================================================
def compare_schema_raw(schema_df, raw_df):

    compare_df = pd.merge(
        schema_df,
        raw_df,
        on=["DATASET", "VARIABLE"],
        how="outer"
    )

    def get_status(row):

        if pd.isna(row.get("SCHEMA_DATATYPE")):
            return "EXTRA_IN_RAW"

        elif pd.isna(row.get("RAW_DATATYPE")):
            return "MISSING_IN_RAW"

        elif row["SCHEMA_DATATYPE_STD"] == row["RAW_DATATYPE_STD"]:
            return "MATCH"

        else:
            return "DATATYPE_MISMATCH"

    compare_df["STATUS"] = compare_df.apply(get_status, axis=1)

    return compare_df


# =========================================================
# 5. 主 pipeline
# =========================================================
def run_pipeline(cube_path, schema_path):

    # ✅ RAW LIST
    raw_df = build_raw_list(cube_path)

    if raw_df.empty:
        raise ValueError("No SAS dataset found")

    # ✅ SCHEMA LIST
    schema_df = build_schema_list(schema_path)

    # ✅ COMPARE
    compare_df = compare_schema_raw(schema_df, raw_df)

    return schema_df, raw_df, compare_df


