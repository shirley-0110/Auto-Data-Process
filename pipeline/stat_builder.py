
import os
import json
import pandas as pd
import pyreadstat


# =========================================================
# 固定欄位（避免 empty dataframe 沒欄位時 merge 出錯）
# =========================================================
SCHEMA_COLUMNS = [
    "SOURCE",
    "DATASET",
    "VARIABLE",
    "LABEL",
    "SCHEMA_DATATYPE",
    "SCHEMA_DATATYPE_STD",
]

RAW_COLUMNS = [
    "SOURCE",
    "DATASET",
    "VARIABLE",
    "RAW_DATATYPE",
    "RAW_DATATYPE_STD",
    "RAW_SAMPLE",
]

COMPARE_COLUMNS = [
    "DATASET",
    "VARIABLE",
    "LABEL",
    "SCHEMA_DATATYPE",
    "SCHEMA_DATATYPE_STD",
    "RAW_DATATYPE",
    "RAW_DATATYPE_STD",
    "RAW_SAMPLE",
    "STATUS",
]


# =========================================================
# 1) 找真正放 .sas7bdat 的資料夾
# =========================================================
def find_sas_folder(base):
    """
    遞迴搜尋第一個含有 .sas7bdat 的資料夾
    """
    for root, dirs, files in os.walk(base):
        for f in files:
            if str(f).lower().endswith(".sas7bdat"):
                return root
    return base


# =========================================================
# 2) datatype normalize
# =========================================================
def normalize_schema_dtype(field_type, data_format):
    """
    將 schema 的 Field Type / Data Format 統一成標準類型
    """
    ft = str(field_type) if pd.notna(field_type) else ""
    dfmt = str(data_format) if pd.notna(data_format) else ""
    text = f"{ft} {dfmt}".lower().strip()

    if "datetime" in text:
        return "DATETIME"
    elif "date" in text or "yyyy" in text or "mmm" in text or "dd-" in text:
        return "DATE"
    elif "time" in text and "date" not in text:
        return "TIME"
    elif any(x in text for x in ["int", "number", "float", "numeric", "decimal"]):
        return "NUMERIC"
    else:
        return "TEXT"


def normalize_raw_dtype(dtype):
    """
    將 pandas / pyreadstat 讀到的 raw dtype 統一成標準類型
    """
    d = str(dtype).lower()

    if "datetime" in d:
        return "DATETIME"
    elif "date" in d:
        return "DATE"
    elif "int" in d or "float" in d or "double" in d:
        return "NUMERIC"
    else:
        return "TEXT"


# =========================================================
# 3) schema header 偵測
# =========================================================
def detect_header_row(df, max_rows=20):
    """
    在前幾列中找真正 header row：
    只要某列含有 Field Name 或 Field OID 就視為 header
    """
    scan_n = min(len(df), max_rows)

    for i in range(scan_n):
        row_values = [str(x).strip().lower() if pd.notna(x) else "" for x in df.iloc[i]]

        has_field_name = any("field name" in x for x in row_values)
        has_field_oid = any("field oid" in x for x in row_values)

        if has_field_name or has_field_oid:
            return i

    return None


def read_schema_sheet(xls, sheet_name):
    """
    先無 header 讀整張 sheet，再找真正 header row，之後重讀
    """
    preview = pd.read_excel(xls, sheet_name=sheet_name, header=None, dtype=object)
    header_row = detect_header_row(preview)

    if header_row is None:
        return None

    df = pd.read_excel(xls, sheet_name=sheet_name, header=header_row, dtype=object)
    df.columns = [str(c).strip() for c in df.columns]
    return df


# =========================================================
# 4) 建立 RAW LIST（含 sample values）
# =========================================================
def build_raw_list(cube_path):
    """
    從 CRScube / SAS 資料夾建立 raw variable list
    每列代表一個 dataset-variable
    """
    cube_path = find_sas_folder(cube_path)

    records = []

    if not os.path.exists(cube_path):
        return pd.DataFrame(columns=RAW_COLUMNS)

    for f in os.listdir(cube_path):
        if not str(f).lower().endswith(".sas7bdat"):
            continue

        dataset = os.path.splitext(f)[0].upper()
        full_path = os.path.join(cube_path, f)

        try:
            df, meta = pyreadstat.read_sas7bdat(full_path)
        except Exception as e:
            print(f"FAILED to read {f}: {e}")
            continue

        for col in df.columns:
            series = df[col]

            # sample 取前5筆非空值
            sample_values = series.dropna().astype(str).head(5).tolist()

            records.append({
                "SOURCE": "RAW",
                "DATASET": dataset,
                "VARIABLE": str(col).strip().upper(),
                "RAW_DATATYPE": str(series.dtype),
                "RAW_DATATYPE_STD": normalize_raw_dtype(series.dtype),
                "RAW_SAMPLE": json.dumps(sample_values, ensure_ascii=False)
            })

    if not records:
        return pd.DataFrame(columns=RAW_COLUMNS)

    return pd.DataFrame(records, columns=RAW_COLUMNS)


# =========================================================
# 5) 建立 SCHEMA LIST
# =========================================================
def build_schema_list(schema_path):
    """
    從 eCRF schema 建立 variable list
    預設每個 sheet = 一個 dataset（先用 sheet name 當 DATASET）
    後續如果你的 schema 有 dataset abbreviation 專屬欄位，再升級這裡
    """
    records = []

    xls = pd.ExcelFile(schema_path)

    for sheet in xls.sheet_names:
        df = read_schema_sheet(xls, sheet)

        if df is None or df.empty:
            continue

        # 找關鍵欄位
        field_name_col = None
        field_oid_col = None
        field_type_col = None
        data_format_col = None

        for col in df.columns:
            c = str(col).strip().lower()

            if "field name" in c:
                field_name_col = col
            elif "field oid" in c:
                field_oid_col = col
            elif "field type" in c:
                field_type_col = col
            elif "data format" in c:
                data_format_col = col

        # 沒有 field name / field oid 就跳過
        if field_name_col is None and field_oid_col is None:
            continue

        for _, row in df.iterrows():
            field_name = row[field_name_col] if field_name_col in df.columns else None
            field_oid = row[field_oid_col] if field_oid_col in df.columns else None
            field_type = row[field_type_col] if field_type_col in df.columns else None
            data_format = row[data_format_col] if data_format_col in df.columns else None

            # 只抓真正 variable 列
            if pd.isna(field_name) and pd.isna(field_oid):
                continue

            if pd.notna(field_oid) and str(field_oid).strip():
                variable = str(field_oid).strip().upper()
            elif pd.notna(field_name) and str(field_name).strip():
                variable = str(field_name).strip().upper()
            else:
                continue

            label = str(field_name).strip() if pd.notna(field_name) else None

            ft = str(field_type).strip() if pd.notna(field_type) else ""
            dfmt = str(data_format).strip() if pd.notna(data_format) else ""

            dtype_raw = " / ".join([x for x in [ft, dfmt] if x]) if (ft or dfmt) else "UNKNOWN"

            records.append({
                "SOURCE": "SCHEMA",
                "DATASET": str(sheet).strip().upper(),
                "VARIABLE": variable,
                "LABEL": label,
                "SCHEMA_DATATYPE": dtype_raw,
                "SCHEMA_DATATYPE_STD": normalize_schema_dtype(field_type, data_format)
            })

    if not records:
        return pd.DataFrame(columns=SCHEMA_COLUMNS)

    return pd.DataFrame(records, columns=SCHEMA_COLUMNS)


# =========================================================
# 6) 比較 schema vs raw
# =========================================================
def compare_schema_raw(schema_df, raw_df):
    """
    依 DATASET + VARIABLE 比對 schema / raw
    """
    # 保底：即使空也要有欄位
    if schema_df is None or schema_df.empty:
        schema_df = pd.DataFrame(columns=SCHEMA_COLUMNS)
    else:
        for c in SCHEMA_COLUMNS:
            if c not in schema_df.columns:
                schema_df[c] = pd.NA
        schema_df = schema_df[SCHEMA_COLUMNS]

    if raw_df is None or raw_df.empty:
        raw_df = pd.DataFrame(columns=RAW_COLUMNS)
    else:
        for c in RAW_COLUMNS:
            if c not in raw_df.columns:
                raw_df[c] = pd.NA
        raw_df = raw_df[RAW_COLUMNS]

    compare_df = pd.merge(
        schema_df,
        raw_df,
        on=["DATASET", "VARIABLE"],
        how="outer"
    )

    def get_status(row):
        schema_missing = pd.isna(row.get("SCHEMA_DATATYPE"))
        raw_missing = pd.isna(row.get("RAW_DATATYPE"))

        if schema_missing and not raw_missing:
            return "EXTRA_IN_RAW"
        elif raw_missing and not schema_missing:
            return "MISSING_IN_RAW"
        elif schema_missing and raw_missing:
            return "UNKNOWN"
        elif row["SCHEMA_DATATYPE_STD"] == row["RAW_DATATYPE_STD"]:
            return "MATCH"
        else:
            return "DATATYPE_MISMATCH"

    compare_df["STATUS"] = compare_df.apply(get_status, axis=1)

    for c in COMPARE_COLUMNS:
        if c not in compare_df.columns:
            compare_df[c] = pd.NA

    return compare_df[COMPARE_COLUMNS]


# =========================================================
# 7) 主流程
# =========================================================
def run_pipeline(cube_path, schema_path):
    """
    回傳：
    - schema_df
    - raw_df
    - compare_df
    """
    raw_df = build_raw_list(cube_path)
    schema_df = build_schema_list(schema_path)
    compare_df = compare_schema_raw(schema_df, raw_df)

    return schema_df, raw_df, compare_df
