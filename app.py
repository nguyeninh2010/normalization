import streamlit as st
import pandas as pd
import bibtexparser
from io import BytesIO
import re

OUTPUT_COLUMNS = [
    "Title", "Authors", "Author full names", "Affiliations",
    "DE", "ID", "DE_ID", "Keyword_Source",
    "References", "DOI", "Year", "Source title",
    "Volume", "Issue", "Page start", "Page end"
]

# =========================
# HÀM LÀM SẠCH CƠ BẢN
# =========================
def clean_text(x):
    if pd.isna(x):
        return ""
    x = str(x).strip()
    x = re.sub(r"\s+", " ", x)
    return x

def clean_doi(x):
    x = clean_text(x).lower()
    x = x.replace("https://doi.org/", "")
    x = x.replace("http://doi.org/", "")
    x = x.replace("doi:", "")
    return x.strip()

def normalize_title(x):
    x = clean_text(x).lower()
    x = re.sub(r"[^\w\s]", " ", x)
    x = re.sub(r"\s+", " ", x).strip()
    return x

def split_pages(pages):
    page_start, page_end = "", ""
    pages = clean_text(pages)
    if "-" in pages:
        parts = pages.split("-")
        page_start = parts[0].strip()
        page_end = parts[-1].strip()
    return page_start, page_end

def pick_first_nonempty(entry, keys):
    for k in keys:
        v = entry.get(k, "")
        if clean_text(v):
            return v
    return ""

# =========================
# CHUẨN HÓA TỪ KHÓA
# =========================
def standardize_keyword_token(token):
    token = clean_text(token).lower()
    token = token.strip(" .;,:")

    token = token.replace("&", "and")
    token = re.sub(r"[-_/]+", " ", token)
    token = re.sub(r"\s+", " ", token).strip()

    replacements = {
        "agri tourism": "agritourism",
        "agri tourist": "agritourism",
        "agri tourisms": "agritourism",
        "agro tourism": "agrotourism",
        "agro tourisms": "agrotourism",
        "agro tourist": "agrotourism",
        "farm based tourism": "farm tourism",
        "farm stay tourism": "farm tourism",
        "rural touirsm": "rural tourism",
        "sustainable developement": "sustainable development",
        "behavioural intention": "behavioral intention",
        "tourist behaviour": "tourist behavior",
        "consumer behaviour": "consumer behavior"
    }

    if token in replacements:
        token = replacements[token]

    return token

def normalize_keywords(value):
    value = clean_text(value)
    if not value:
        return ""

    value = value.replace("|", ";")
    value = value.replace(",", ";")

    parts = [p.strip() for p in value.split(";") if p.strip()]

    seen = set()
    result = []

    for p in parts:
        p_std = standardize_keyword_token(p)
        if p_std and p_std not in seen:
            seen.add(p_std)
            result.append(p_std)

    return "; ".join(result)

def merge_keyword_fields(*values):
    items = []
    seen = set()

    for value in values:
        value = normalize_keywords(value)
        if not value:
            continue

        for part in value.split(";"):
            p = part.strip()
            if p and p not in seen:
                seen.add(p)
                items.append(p)

    return "; ".join(items)

def detect_keyword_source(de, id_):
    has_de = clean_text(de) != ""
    has_id = clean_text(id_) != ""

    if has_de and has_id:
        return "DE+ID"
    elif has_de:
        return "DE only"
    elif has_id:
        return "ID only"
    else:
        return "No keywords"

# =========================
# CHUẨN HÓA TÊN CỘT
# =========================
def standardize_columns(df):
    df = df.copy()
    df.columns = [clean_text(c) for c in df.columns]

    rename_map = {
        "Article Title": "Title",
        "TI": "Title",

        "Authors": "Authors",
        "AU": "Authors",

        "Author full names": "Author full names",
        "Author Full Names": "Author full names",
        "AF": "Author full names",

        "Affiliations": "Affiliations",
        "C1": "Affiliations",

        "DE": "DE",
        "Author Keywords": "DE",
        "Author keywords": "DE",

        "ID": "ID",
        "Index Keywords": "ID",
        "Keywords Plus": "ID",
        "Keywords plus": "ID",

        "References": "References",
        "CR": "References",

        "DOI": "DOI",
        "DI": "DOI",

        "Year": "Year",
        "PY": "Year",

        "Source title": "Source title",
        "SO": "Source title",
        "JI": "Source title",
        "Journal": "Source title",

        "Volume": "Volume",
        "VL": "Volume",

        "Issue": "Issue",
        "IS": "Issue",
        "Number": "Issue",

        "Page start": "Page start",
        "BP": "Page start",

        "Page end": "Page end",
        "EP": "Page end",
    }

    df = df.rename(columns={c: rename_map.get(c, c) for c in df.columns})

    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df["DOI"] = df["DOI"].apply(clean_doi)
    df["Title"] = df["Title"].apply(clean_text)
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce").astype("Int64")
    df["Title_key"] = df["Title"].apply(normalize_title)

    df["DE"] = df["DE"].apply(normalize_keywords)
    df["ID"] = df["ID"].apply(normalize_keywords)
    df["DE_ID"] = df.apply(lambda row: merge_keyword_fields(row["DE"], row["ID"]), axis=1)
    df["Keyword_Source"] = df.apply(lambda row: detect_keyword_source(row["DE"], row["ID"]), axis=1)

    return df

# =========================
# ĐỌC BIBTEX
# =========================
def convert_bibtex_to_standard_structure(bib_data):
    records = []

    for entry in bib_data.entries:
        page_start, page_end = split_pages(entry.get("pages", ""))

        title = pick_first_nonempty(entry, ["title", "Title"])
        authors = pick_first_nonempty(entry, ["author", "authors", "AU"])
        journal = pick_first_nonempty(entry, ["journal", "journaltitle", "booktitle", "SO"])
        doi = pick_first_nonempty(entry, ["doi", "DOI", "di", "DI"])
        year = pick_first_nonempty(entry, ["year", "PY"])
        volume = pick_first_nonempty(entry, ["volume", "VL"])
        issue = pick_first_nonempty(entry, ["number", "issue", "IS"])
        affiliations = pick_first_nonempty(entry, ["affiliations", "C1"])

        de = pick_first_nonempty(
            entry,
            ["keywords", "keyword", "author_keywords", "de", "DE"]
        )

        id_ = pick_first_nonempty(
            entry,
            ["keywords-plus", "keywords_plus", "id", "ID", "index_keywords"]
        )

        references = pick_first_nonempty(
            entry,
            ["cited-references", "references", "CR"]
        )

        record = {
            "Title": title,
            "Authors": authors,
            "Author full names": authors,
            "Affiliations": affiliations,
            "DE": de,
            "ID": id_,
            "References": references,
            "DOI": doi,
            "Year": year,
            "Source title": journal,
            "Volume": volume,
            "Issue": issue,
            "Page start": page_start,
            "Page end": page_end
        }
        records.append(record)

    df = pd.DataFrame(records)
    return standardize_columns(df)

# =========================
# ĐỌC CSV/XLSX
# =========================
def convert_excel_or_csv(file):
    ext = file.name.split(".")[-1].lower()

    if ext == "xlsx":
        df = pd.read_excel(file)
    elif ext == "csv":
        try:
            df = pd.read_csv(file, encoding="utf-8")
        except Exception:
            file.seek(0)
            df = pd.read_csv(file, encoding="latin1")
    else:
        df = pd.DataFrame()

    return standardize_columns(df)

# =========================
# XUẤT FILE
# =========================
def convert_df(df):
    output = BytesIO()
    df.to_csv(output, index=False, encoding="utf-8-sig")
    return output.getvalue()

# =========================
# GỘP 2 CỘT ƯU TIÊN GIÁ TRỊ CÓ SẴN
# =========================
def combine_two_columns(series_a, series_b):
    a = series_a.copy()
    b = series_b.copy()
    return a.combine_first(b)

# =========================
# GHÉP NHÓM CÓ DOI
# =========================
def merge_main_records(merged_doi):
    final = pd.DataFrame()
    final["DOI"] = merged_doi["DOI"]

    simple_cols = [
        "Title", "Authors", "Author full names", "Affiliations",
        "References", "Year", "Source title", "Volume", "Issue",
        "Page start", "Page end"
    ]

    for col in simple_cols:
        col_scopus = f"{col}_scopus"
        col_isi = f"{col}_isi"

        if col_scopus in merged_doi.columns and col_isi in merged_doi.columns:
            final[col] = combine_two_columns(merged_doi[col_scopus], merged_doi[col_isi])
        elif col_scopus in merged_doi.columns:
            final[col] = merged_doi[col_scopus]
        elif col_isi in merged_doi.columns:
            final[col] = merged_doi[col_isi]
        else:
            final[col] = pd.Series([""] * len(merged_doi))

    final["DE"] = merged_doi.apply(
        lambda row: merge_keyword_fields(
            row.get("DE_scopus", ""),
            row.get("DE_isi", "")
        ),
        axis=1
    )

    final["ID"] = merged_doi.apply(
        lambda row: merge_keyword_fields(
            row.get("ID_scopus", ""),
            row.get("ID_isi", "")
        ),
        axis=1
    )

    final["DE_ID"] = final.apply(lambda row: merge_keyword_fields(row["DE"], row["ID"]), axis=1)
    final["Keyword_Source"] = final.apply(lambda row: detect_keyword_source(row["DE"], row["ID"]), axis=1)
    final["Title_key"] = final["Title"].apply(normalize_title)
    final["Year"] = pd.to_numeric(final["Year"], errors="coerce").astype("Int64")

    return final

# =========================
# TẠO FILE CHUẨN CHO VOSVIEWER
# =========================
def create_vosviewer_export(df, keyword_mode="DE"):
    vos = df.copy()

    if keyword_mode == "DE":
        vos["Author Keywords"] = vos["DE"]
        vos["Index Keywords"] = vos["ID"]
    elif keyword_mode == "DE_ID":
        vos["Author Keywords"] = vos["DE_ID"]
        vos["Index Keywords"] = vos["ID"]
    else:
        vos["Author Keywords"] = vos["DE"]
        vos["Index Keywords"] = vos["ID"]

    export_cols = [
        "Title",
        "Authors",
        "Author Keywords",
        "Index Keywords",
        "Year",
        "Source title",
        "DOI"
    ]

    for col in export_cols:
        if col not in vos.columns:
            vos[col] = ""

    return vos[export_cols]

# =========================
# GIAO DIỆN
# =========================
st.set_page_config(page_title="Kết nối dữ liệu ISI & Scopus", layout="wide")
st.title("📘 Kết nối dữ liệu ISI & Scopus theo chuẩn phân tích từ khóa")

st.markdown("### Tùy chọn export cho VOSviewer")
keyword_mode = st.radio(
    "Chọn cách đưa từ khóa vào cột Author Keywords",
    options=["DE", "DE_ID"],
    index=0,
    horizontal=True
)

if keyword_mode == "DE":
    st.caption("Dùng Author Keywords = DE. Phù hợp khi muốn bám sát từ khóa tác giả.")
else:
    st.caption("Dùng Author Keywords = DE_ID. Phù hợp khi muốn mở rộng mạng đồng xuất hiện.")

isi_file = st.file_uploader("📤 Chọn file ISI (.bib, .csv, .xlsx)", type=["bib", "csv", "xlsx"])
scopus_file = st.file_uploader("📤 Chọn file Scopus (.csv, .xlsx)", type=["csv", "xlsx"])

df_isi = pd.DataFrame()
df_scopus = pd.DataFrame()

if isi_file:
    st.subheader("🔎 Dữ liệu từ file ISI")
    try:
        if isi_file.name.lower().endswith(".bib"):
            bib_data = bibtexparser.load(isi_file)
            df_isi = convert_bibtex_to_standard_structure(bib_data)
        else:
            df_isi = convert_excel_or_csv(isi_file)

        st.write("Số bản ghi ISI:", len(df_isi))
        st.write("ISI có DE:", int((df_isi["DE"] != "").sum()))
        st.write("ISI có ID:", int((df_isi["ID"] != "").sum()))
        st.write("ISI có DE_ID:", int((df_isi["DE_ID"] != "").sum()))
        st.dataframe(df_isi.head(5))
    except Exception as e:
        st.error(f"Lỗi khi xử lý file ISI: {e}")

if scopus_file:
    st.subheader("🔎 Dữ liệu từ file Scopus")
    try:
        df_scopus = convert_excel_or_csv(scopus_file)

        st.write("Số bản ghi Scopus:", len(df_scopus))
        st.write("Scopus có DE:", int((df_scopus["DE"] != "").sum()))
        st.write("Scopus có ID:", int((df_scopus["ID"] != "").sum()))
        st.write("Scopus có DE_ID:", int((df_scopus["DE_ID"] != "").sum()))
        st.dataframe(df_scopus.head(5))
    except Exception as e:
        st.error(f"Lỗi khi xử lý file Scopus: {e}")

if not df_isi.empty and not df_scopus.empty:
    st.subheader("🔗 Ghép dữ liệu")

    try:
        isi_with_doi = df_isi[df_isi["DOI"] != ""].copy()
        scopus_with_doi = df_scopus[df_scopus["DOI"] != ""].copy()

        merged_doi = pd.merge(
            isi_with_doi,
            scopus_with_doi,
            on="DOI",
            how="outer",
            suffixes=("_isi", "_scopus")
        )

        final_doi = merge_main_records(merged_doi)

        isi_no_doi = df_isi[df_isi["DOI"] == ""].copy()
        scopus_no_doi = df_scopus[df_scopus["DOI"] == ""].copy()

        no_doi = pd.concat([isi_no_doi, scopus_no_doi], ignore_index=True)
        no_doi["Year"] = pd.to_numeric(no_doi["Year"], errors="coerce").astype("Int64")
        no_doi["Title_key"] = no_doi["Title"].apply(normalize_title)

        no_doi = no_doi.sort_values(by=["Year"], ascending=False, na_position="last")
        no_doi = no_doi.drop_duplicates(subset=["Title_key"], keep="first")

        merged = pd.concat([final_doi, no_doi], ignore_index=True)

        merged["DE"] = merged["DE"].apply(normalize_keywords)
        merged["ID"] = merged["ID"].apply(normalize_keywords)
        merged["DE_ID"] = merged.apply(lambda row: merge_keyword_fields(row["DE"], row["ID"]), axis=1)
        merged["Keyword_Source"] = merged.apply(lambda row: detect_keyword_source(row["DE"], row["ID"]), axis=1)
        merged["Title_key"] = merged["Title"].apply(normalize_title)
        merged["Year"] = pd.to_numeric(merged["Year"], errors="coerce").astype("Int64")

        merged = merged.sort_values(by=["Year"], ascending=False, na_position="last")

        with_doi = merged[merged["DOI"] != ""].drop_duplicates(subset=["DOI"], keep="first")
        without_doi = merged[merged["DOI"] == ""].drop_duplicates(subset=["Title_key"], keep="first")

        merged = pd.concat([with_doi, without_doi], ignore_index=True)

        for col in OUTPUT_COLUMNS:
            if col not in merged.columns:
                merged[col] = ""

        merged = merged[OUTPUT_COLUMNS]

        st.success("✅ Ghép dữ liệu hoàn tất")
        st.write("Tổng số bản ghi sau ghép:", len(merged))
        st.write("Số bản ghi có DE:", int((merged["DE"] != "").sum()))
        st.write("Số bản ghi có ID:", int((merged["ID"] != "").sum()))
        st.write("Số bản ghi có DE_ID:", int((merged["DE_ID"] != "").sum()))

        st.dataframe(merged.head(30))

        # file đầy đủ
        csv_full = convert_df(merged)
        st.download_button(
            "📥 Tải file merged đầy đủ (CSV)",
            data=csv_full,
            file_name="merged_isi_scopus_keywords_cleaned.csv",
            mime="text/csv"
        )

        # file chuẩn VOSviewer
        vos_df = create_vosviewer_export(merged, keyword_mode=keyword_mode)
        csv_vos = convert_df(vos_df)

        st.download_button(
            "📥 Tải file chuẩn cho VOSviewer (CSV)",
            data=csv_vos,
            file_name=f"vosviewer_ready_{keyword_mode.lower()}.csv",
            mime="text/csv"
        )

        st.subheader("🔎 Xem trước file xuất cho VOSviewer")
        st.dataframe(vos_df.head(20))

    except Exception as e:
        st.error(f"Lỗi khi ghép dữ liệu: {e}")
