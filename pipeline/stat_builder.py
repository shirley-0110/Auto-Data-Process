
import os
import pandas as pd
import pyreadstat


# =========================================================
# 固定欄位（避免 empty dataframe 沒欄位）
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
]

COMPARE_COLUMNS = [
    "DATASET",
    "VARIABLE",
    "LABEL",
    "SCHEMA_DATATYPE",
    "SCHEMA_DATATYPE_STD",
    "RAW_DATATYPE",
    "RAW_DATATYPE_STD",
    "STATUS",
]


# =========================================================
# 1. 找 SAS folder
# =========================================================
def find_sas_folder(base):
    for root, dirs, files in os.walk(base):
        for f in files:
            if f.lower().endswith(".sas7bdat"):
                return root
    return base


# =========================================================
# 2. datatype normalization
# =========================================================
def normalize_schema_dtype(field_type, data_format):
    ft = str(field_type).strip().lower() if pd.notna(field_type) else ""
    dfmt = str(data_format).strip().lower() if pd.notna(data_format) else ""
    text = f"{ft} {dfmt}"

    if "date" in text or "dd-" in text or "yyyy" in text or "mmm" in text:
        return "DATE"
    elif "time" in text and "date" not in text:
        return "TIME"
    elif "datetime" in text:
        return "DATETIME"
    elif any(x in text for x in ["int", "float", "number", "numeric", "decimal"]):
        return "NUMERIC"
    else:
        return "TEXT"


def normalize_raw_dtype(dtype_str):
    d = str(dtype_str).lower()
    if "int" in d or "float" in d or "double" in d:
        return "NUMERIC"
    elif "datetime" in d:
        return "DATETIME"
    elif "date" in d:
        return "DATE"
    else:
        return "TEXT"


# =========================================================
# 3. 找 schema sheet 真正 header row
# =========================================================
def detect_header_row(sheet_df, max_scan_rows=20):
    """
    從前幾列找真正 header row：
    只要某一列包含 'Field Name' 或 'Field OID' 就視為 header row
    """
    scan_rows = min(len(sheet_df), max_scan_rows)

    for i in range(scan_rows):
        row_values = [str(x).strip().lower() for x in sheet_df.iloc[i].tolist() if pd.notna(x)]

        has_field_name = any("field name" == x or "field name" in x for x in row_values)
        has_field_oid = any("field oid" == x or "field oid" in x for x in row_values)

        if has_field_name or has_field_oid:
            return i

    return None


def read_schema_sheet_with_detected_header(xls, sheet_name):
    """
    先不設 header 讀整張 sheet，再偵測真正 header row，之後重讀
    """
    preview = pd.read_excel(xls, sheet_name=sheet_name, header=None, dtype=object)
    header_row = detect_header_row(preview)

    if header_row is None:
        return None

    df = pd.read_excel(xls, sheet_name=sheet_name, header=header_row, dtype=object)
    df.columns = [str(c).strip() for c in df.columns]
    return df


# =========================================================
# 4. 建立 RAW LIST
# =========================================================
def build_raw_list(cube_path):
    cube_path = find_sas_folder(cube_path)

    records = []

    if not os.path.exists(cube_path):
        return pd.DataFrame(columns=RAW_COLUMNS)

    for f in os.listdir(cube_path):
        if not f.lower().endswith(".sas7bdat"):
            continue

        dataset = f.split(".")[0].upper()
        full_path = os.path.join(cube_path, f)

        try:
            df, meta = pyreadstat.read_sas7bdat(full_path)
        except Exception as e:
            # 若單一檔案讀失敗，跳過但不中斷全流程
            print(f"FAILED to read {f}: {e}")
            continue

        for col in df.columns:
            dtype = str(df[col].dtype)
            dtype_std = normalize_raw_dtype(dtype)

            records.append({
                "SOURCE": "RAW",
                "DATASET": dataset,
                "VARIABLE": str(col).strip().upper(),
                "RAW_DATATYPE": dtype,
                "RAW_DATATYPE_STD": dtype_std
            })

    if not records:
        return pd.DataFrame(columns=RAW_COLUMNS)

    return pd.DataFrame(records, columns=RAW_COLUMNS)


# =========================================================
# 5. 建立 SCHEMA LIST
# =========================================================
def build_schema_list(schema_path):
    records = []

    xls = pd.ExcelFile(schema_path)

    for sheet in xls.sheet_names:
        df = read_schema_sheet_with_detected_header(xls, sheet)

        if df is None or df.empty:
            continue

        # 欄位名稱標準化
        col_map = {c.lower().strip(): c for c in df.columns}

        # 關鍵欄位
        field_name_col = None
        field_oid_col = None
        field_type_col = None
        data_format_col = None

        for c in df.columns:
            cl = c.lower().strip()
            if cl == "field name" or "field name" in cl:
                field_name_col = c
            elif cl == "field oid" or "field oid" in cl:
                field_oid_col = c
            elif cl == "field type" or "field type" in cl:
                field_type_col = c
            elif cl == "data format" or "data format" in cl:
                data_format_col = c

        # 如果連 Field Name / Field OID 都沒有，就跳過這張 sheet
        if field_name_col is None and field_oid_col is None:
            continue

        for _, row in df.iterrows():
            field_name = row[field_name_col] if field_name_col in df.columns else None
            field_oid = row[field_oid_col] if field_oid_col in df.columns else None
            field_type = row[field_type_col] if field_type_col in df.columns else None
            data_format = row[data_format_col] if data_format_col in df.columns else None

            # 只抓真正有 variable 的列
            if pd.isna(field_name) and pd.isna(field_oid):
                continue

            variable = None
            if pd.notna(field_oid) and str(field_oid).strip():
                variable = str(field_oid).strip().upper()
            elif pd.notna(field_name) and str(field_name).strip():
                variable = str(field_name).strip().upper()
            else:
                continue

            label = str(field_name).strip() if pd.notna(field_name) else None
            dtype_raw = " / ".join([
                str(x).strip() for x in [field_type, data_format] if pd.notna(x) and str(x).strip()
            ]) or "UNKNOWN"

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
# 6. 比較 Schema vs Raw
# =========================================================
def compare_schema_raw(schema_df, raw_df):
    # 保底：即使 empty 也確保有欄位
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

    # 補齊欄位順序
    for c in COMPARE_COLUMNS:
        if c not in compare_df.columns:
            compare_df[c] = pd.NA

    return compare_df[COMPARE_COLUMNS]


# =========================================================
# 7. 主 pipeline
# =========================================================
def run_pipeline(cube_path, schema_path):
    raw_df = build_raw_list(cube_path)
    schema_df = build_schema_list(schema_path)
    compare_df = compare_schema_raw(schema_df, raw_df)
    return schema_df, raw_df, compare_df


