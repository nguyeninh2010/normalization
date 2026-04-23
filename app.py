import streamlit as st
import pandas as pd
import bibtexparser
from io import BytesIO
import re
from difflib import SequenceMatcher

# =========================
# CẤU HÌNH
# =========================
OUTPUT_COLUMNS = [
    "Title", "Authors", "Author full names", "Affiliations",
    "DE", "ID", "DE_ID", "Keyword_Source",
    "References", "DOI", "Year", "Source title",
    "Volume", "Issue", "Page start", "Page end"
]

VOS_COLUMNS = [
    "Title", "Authors", "Author Keywords", "Index Keywords",
    "Year", "Source title", "DOI"
]

CONTROLLED_SYNONYMS = {
    "agri tourism": "agritourism",
    "agri tourist": "agritourism",
    "agri tourisms": "agritourism",
    "agro tourism": "agrotourism",
    "agro tourist": "agrotourism",
    "agro tourisms": "agrotourism",
    "agricultural tourism": "agritourism",
    "farm tourism": "agritourism",
    "farm based tourism": "agritourism",
    "farm stay tourism": "agritourism",
    "rural touirsm": "rural tourism",
    "sustainable developement": "sustainable development",
    "behaviour": "behavior",
    "behavioural": "behavioral",
    "behavioural intention": "behavioral intention",
    "tourist behaviour": "tourist behavior",
    "consumer behaviour": "consumer behavior",
}

NOISE_TERMS_DEFAULT = {
    "article", "review", "study", "studies", "approach", "impact",
    "model", "models", "strategy", "strategies", "analysis",
    "china", "spain", "italy", "poland", "romania", "eurasia",
    "covid 19", "covid-19"
}

# =========================
# HÀM CƠ BẢN
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

def singularize_simple(token: str) -> str:
    token = clean_text(token)

    protected = {
        "economics", "ethics", "politics", "physics", "mathematics",
        "sustainability", "hospitality", "analysis"
    }
    if token in protected:
        return token

    if len(token) <= 4:
        return token

    if token.endswith("ies") and len(token) > 5:
        return token[:-3] + "y"

    if token.endswith("sses") or token.endswith("ss"):
        return token

    if token.endswith("s") and not token.endswith("us") and not token.endswith("is"):
        return token[:-1]

    return token

# =========================
# CHUẨN HÓA TỪ KHÓA
# =========================
def standardize_keyword_token(
    token,
    apply_plural_normalization=True,
    custom_synonyms=None
):
    token = clean_text(token).lower()
    token = token.strip(" .;,:")

    token = token.replace("&", "and")
    token = re.sub(r"[-_/]+", " ", token)
    token = re.sub(r"\s+", " ", token).strip()

    if apply_plural_normalization:
        words = token.split()
        words = [singularize_simple(w) for w in words]
        token = " ".join(words)

    synonym_map = dict(CONTROLLED_SYNONYMS)
    if custom_synonyms:
        synonym_map.update(custom_synonyms)

    token = synonym_map.get(token, token)
    return token

def normalize_keywords(
    value,
    apply_plural_normalization=True,
    custom_synonyms=None,
    remove_noise=False
):
    value = clean_text(value)
    if not value:
        return ""

    value = value.replace("|", ";")
    value = value.replace(",", ";")

    parts = [p.strip() for p in value.split(";") if p.strip()]

    seen = set()
    result = []

    for p in parts:
        p_std = standardize_keyword_token(
            p,
            apply_plural_normalization=apply_plural_normalization,
            custom_synonyms=custom_synonyms
        )

        if remove_noise and p_std in NOISE_TERMS_DEFAULT:
            continue

        if p_std and p_std not in seen:
            seen.add(p_std)
            result.append(p_std)

    return "; ".join(result)

def merge_keyword_fields(
    *values,
    apply_plural_normalization=True,
    custom_synonyms=None,
    remove_noise=False
):
    items = []
    seen = set()

    for value in values:
        value = normalize_keywords(
            value,
            apply_plural_normalization=apply_plural_normalization,
            custom_synonyms=custom_synonyms,
            remove_noise=remove_noise
        )
        if not value:
            continue

        for part in value.split(";"):
            p = part.strip()
            if p and p not in seen:
                seen.add(p)
                items.append(p)

    return "; ".join(items)

def apply_mapping_to_keyword_string(value, mapping_dict):
    value = clean_text(value)
    if not value:
        return ""

    parts = [p.strip() for p in value.split(";") if p.strip()]
    out = []
    seen = set()

    for p in parts:
        new_p = mapping_dict.get(p, p)
        new_p = clean_text(new_p)
        if new_p and new_p not in seen:
            seen.add(new_p)
            out.append(new_p)

    return "; ".join(out)

def detect_keyword_source(de, id_):
    has_de = clean_text(de) != ""
    has_id = clean_text(id_) != ""

    if has_de and has_id:
        return "DE+ID"
    if has_de:
        return "DE only"
    if has_id:
        return "ID only"
    return "No keywords"

# =========================
# CHUẨN HÓA CỘT
# =========================
def standardize_columns(
    df,
    apply_plural_normalization=True,
    custom_synonyms=None,
    remove_noise=False
):
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

    df["DE"] = df["DE"].apply(
        lambda x: normalize_keywords(
            x,
            apply_plural_normalization=apply_plural_normalization,
            custom_synonyms=custom_synonyms,
            remove_noise=remove_noise
        )
    )
    df["ID"] = df["ID"].apply(
        lambda x: normalize_keywords(
            x,
            apply_plural_normalization=apply_plural_normalization,
            custom_synonyms=custom_synonyms,
            remove_noise=remove_noise
        )
    )
    df["DE_ID"] = df.apply(
        lambda row: merge_keyword_fields(
            row["DE"], row["ID"],
            apply_plural_normalization=apply_plural_normalization,
            custom_synonyms=custom_synonyms,
            remove_noise=remove_noise
        ),
        axis=1
    )
    df["Keyword_Source"] = df.apply(lambda row: detect_keyword_source(row["DE"], row["ID"]), axis=1)

    return df

# =========================
# ĐỌC FILE
# =========================
def convert_bibtex_to_standard_structure(
    bib_data,
    apply_plural_normalization=True,
    custom_synonyms=None,
    remove_noise=False
):
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

        de = pick_first_nonempty(entry, ["keywords", "keyword", "author_keywords", "de", "DE"])
        id_ = pick_first_nonempty(entry, ["keywords-plus", "keywords_plus", "id", "ID", "index_keywords"])
        references = pick_first_nonempty(entry, ["cited-references", "references", "CR"])

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
    return standardize_columns(
        df,
        apply_plural_normalization=apply_plural_normalization,
        custom_synonyms=custom_synonyms,
        remove_noise=remove_noise
    )

def convert_excel_or_csv(
    file,
    apply_plural_normalization=True,
    custom_synonyms=None,
    remove_noise=False
):
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

    return standardize_columns(
        df,
        apply_plural_normalization=apply_plural_normalization,
        custom_synonyms=custom_synonyms,
        remove_noise=remove_noise
    )

# =========================
# GHÉP DỮ LIỆU
# =========================
def combine_two_columns(series_a, series_b):
    return series_a.copy().combine_first(series_b.copy())

def merge_main_records(
    merged_doi,
    apply_plural_normalization=True,
    custom_synonyms=None,
    remove_noise=False
):
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
            row.get("DE_isi", ""),
            apply_plural_normalization=apply_plural_normalization,
            custom_synonyms=custom_synonyms,
            remove_noise=remove_noise
        ),
        axis=1
    )

    final["ID"] = merged_doi.apply(
        lambda row: merge_keyword_fields(
            row.get("ID_scopus", ""),
            row.get("ID_isi", ""),
            apply_plural_normalization=apply_plural_normalization,
            custom_synonyms=custom_synonyms,
            remove_noise=remove_noise
        ),
        axis=1
    )

    final["DE_ID"] = final.apply(
        lambda row: merge_keyword_fields(
            row["DE"], row["ID"],
            apply_plural_normalization=apply_plural_normalization,
            custom_synonyms=custom_synonyms,
            remove_noise=remove_noise
        ),
        axis=1
    )
    final["Keyword_Source"] = final.apply(lambda row: detect_keyword_source(row["DE"], row["ID"]), axis=1)
    final["Title_key"] = final["Title"].apply(normalize_title)
    final["Year"] = pd.to_numeric(final["Year"], errors="coerce").astype("Int64")

    return final

# =========================
# GỢI Ý TỪ KHÓA GẦN GIỐNG
# =========================
def extract_keyword_frequency(df, field="DE_ID"):
    keywords = []
    if field not in df.columns:
        return pd.DataFrame(columns=["keyword", "count"])

    for value in df[field].fillna(""):
        if clean_text(value):
            keywords.extend([x.strip() for x in str(value).split(";") if x.strip()])

    if not keywords:
        return pd.DataFrame(columns=["keyword", "count"])

    freq = pd.Series(keywords).value_counts().reset_index()
    freq.columns = ["keyword", "count"]
    return freq

def suggest_similar_keywords(freq_df, min_count=2, similarity_threshold=0.90, max_suggestions=200):
    if freq_df.empty:
        return pd.DataFrame(columns=["Use", "Original", "Suggested", "Count Original", "Count Suggested", "Similarity"])

    candidates = freq_df[freq_df["count"] >= min_count]["keyword"].tolist()
    counts = dict(zip(freq_df["keyword"], freq_df["count"]))

    suggestions = []
    seen_pairs = set()

    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            k1 = candidates[i]
            k2 = candidates[j]

            if len(k1) < 4 or len(k2) < 4:
                continue

            sim = SequenceMatcher(None, k1, k2).ratio()

            if sim >= similarity_threshold:
                pair_key = tuple(sorted([k1, k2]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                # gợi ý term có count cao hơn làm chuẩn
                if counts.get(k1, 0) >= counts.get(k2, 0):
                    original = k2
                    suggested = k1
                    count_original = counts.get(k2, 0)
                    count_suggested = counts.get(k1, 0)
                else:
                    original = k1
                    suggested = k2
                    count_original = counts.get(k1, 0)
                    count_suggested = counts.get(k2, 0)

                suggestions.append({
                    "Use": False,
                    "Original": original,
                    "Suggested": suggested,
                    "Count Original": count_original,
                    "Count Suggested": count_suggested,
                    "Similarity": round(sim, 3)
                })

    suggestions_df = pd.DataFrame(suggestions)
    if suggestions_df.empty:
        return suggestions_df

    suggestions_df = suggestions_df.sort_values(
        by=["Similarity", "Count Suggested", "Count Original"],
        ascending=[False, False, False]
    ).head(max_suggestions)

    return suggestions_df

# =========================
# ÁP DỤNG MAPPING ĐƯỢC DUYỆT
# =========================
def rebuild_keywords_after_mapping(df, approved_mapping):
    df = df.copy()

    df["DE"] = df["DE"].apply(lambda x: apply_mapping_to_keyword_string(x, approved_mapping))
    df["ID"] = df["ID"].apply(lambda x: apply_mapping_to_keyword_string(x, approved_mapping))
    df["DE_ID"] = df.apply(lambda row: merge_keyword_fields(row["DE"], row["ID"], apply_plural_normalization=False), axis=1)
    df["Keyword_Source"] = df.apply(lambda row: detect_keyword_source(row["DE"], row["ID"]), axis=1)

    return df

def editor_to_mapping_dict(editor_df):
    mapping = {}
    if editor_df is None or editor_df.empty:
        return mapping

    temp = editor_df.copy()

    for _, row in temp.iterrows():
        use_flag = row.get("Use", False)
        original = clean_text(row.get("Original", ""))
        suggested = clean_text(row.get("Suggested", ""))

        if bool(use_flag) and original and suggested and original != suggested:
            mapping[original] = suggested

    return mapping

# =========================
# XUẤT FILE
# =========================
def convert_df(df):
    output = BytesIO()
    df.to_csv(output, index=False, encoding="utf-8-sig")
    return output.getvalue()

def create_vosviewer_export(df, keyword_mode="DE"):
    vos = df.copy()

    if keyword_mode == "DE":
        vos["Author Keywords"] = vos["DE"]
        vos["Index Keywords"] = vos["ID"]
    else:
        vos["Author Keywords"] = vos["DE_ID"]
        vos["Index Keywords"] = vos["ID"]

    for col in VOS_COLUMNS:
        if col not in vos.columns:
            vos[col] = ""

    return vos[VOS_COLUMNS]

def parse_custom_synonyms(text):
    synonym_map = {}
    lines = text.splitlines()
    for line in lines:
        line = clean_text(line)
        if not line or "=" not in line:
            continue
        left, right = line.split("=", 1)
        left = clean_text(left).lower()
        right = clean_text(right).lower()
        if left and right:
            synonym_map[left] = right
    return synonym_map

# =========================
# SESSION STATE
# =========================
if "merged_base" not in st.session_state:
    st.session_state["merged_base"] = None

if "merged_final" not in st.session_state:
    st.session_state["merged_final"] = None

if "mapping_editor_df" not in st.session_state:
    st.session_state["mapping_editor_df"] = pd.DataFrame()

if "approved_mapping" not in st.session_state:
    st.session_state["approved_mapping"] = {}

# =========================
# GIAO DIỆN
# =========================
st.set_page_config(page_title="Keyword normalization with editable mapping", layout="wide")
st.title("📘 Kết nối dữ liệu ISI & Scopus với bảng chỉnh sửa từ khóa")

st.markdown("### Cấu hình chuẩn hóa")

c1, c2, c3 = st.columns(3)

with c1:
    keyword_mode = st.radio(
        "Export cho VOSviewer",
        options=["DE", "DE_ID"],
        index=0
    )

with c2:
    apply_plural_normalization = st.checkbox(
        "Tầng 2: chuẩn hóa số ít/số nhiều nhẹ",
        value=True
    )

with c3:
    remove_noise = st.checkbox(
        "Bỏ từ khóa nhiễu phổ biến",
        value=False
    )

st.markdown("### Đồng nghĩa có kiểm soát")
default_synonym_text = """agricultural tourism = agritourism
farm tourism = agritourism
farm based tourism = agritourism
agri tourism = agritourism
agro tourism = agrotourism
rural touirsm = rural tourism
behavioural intention = behavioral intention
tourist behaviour = tourist behavior
consumer behaviour = consumer behavior"""

custom_synonym_text = st.text_area(
    "Mỗi dòng theo dạng: biến thể = từ chuẩn",
    value=default_synonym_text,
    height=160
)
custom_synonyms = parse_custom_synonyms(custom_synonym_text)

st.markdown("### Tải dữ liệu")
isi_file = st.file_uploader("📤 Chọn file ISI (.bib, .csv, .xlsx)", type=["bib", "csv", "xlsx"])
scopus_file = st.file_uploader("📤 Chọn file Scopus (.csv, .xlsx)", type=["csv", "xlsx"])

if isi_file and scopus_file:
    try:
        if isi_file.name.lower().endswith(".bib"):
            bib_data = bibtexparser.load(isi_file)
            df_isi = convert_bibtex_to_standard_structure(
                bib_data,
                apply_plural_normalization=apply_plural_normalization,
                custom_synonyms=custom_synonyms,
                remove_noise=remove_noise
            )
        else:
            df_isi = convert_excel_or_csv(
                isi_file,
                apply_plural_normalization=apply_plural_normalization,
                custom_synonyms=custom_synonyms,
                remove_noise=remove_noise
            )

        df_scopus = convert_excel_or_csv(
            scopus_file,
            apply_plural_normalization=apply_plural_normalization,
            custom_synonyms=custom_synonyms,
            remove_noise=remove_noise
        )

        st.subheader("Bước 1. Dữ liệu sau chuẩn hóa ban đầu")
        x1, x2 = st.columns(2)
        with x1:
            st.write("ISI:", len(df_isi), "bản ghi")
            st.write("ISI có DE:", int((df_isi["DE"] != "").sum()))
            st.write("ISI có ID:", int((df_isi["ID"] != "").sum()))
        with x2:
            st.write("Scopus:", len(df_scopus), "bản ghi")
            st.write("Scopus có DE:", int((df_scopus["DE"] != "").sum()))
            st.write("Scopus có ID:", int((df_scopus["ID"] != "").sum()))

        isi_with_doi = df_isi[df_isi["DOI"] != ""].copy()
        scopus_with_doi = df_scopus[df_scopus["DOI"] != ""].copy()

        merged_doi = pd.merge(
            isi_with_doi,
            scopus_with_doi,
            on="DOI",
            how="outer",
            suffixes=("_isi", "_scopus")
        )

        final_doi = merge_main_records(
            merged_doi,
            apply_plural_normalization=apply_plural_normalization,
            custom_synonyms=custom_synonyms,
            remove_noise=remove_noise
        )

        isi_no_doi = df_isi[df_isi["DOI"] == ""].copy()
        scopus_no_doi = df_scopus[df_scopus["DOI"] == ""].copy()

        no_doi = pd.concat([isi_no_doi, scopus_no_doi], ignore_index=True)
        no_doi["Year"] = pd.to_numeric(no_doi["Year"], errors="coerce").astype("Int64")
        no_doi["Title_key"] = no_doi["Title"].apply(normalize_title)
        no_doi = no_doi.sort_values(by=["Year"], ascending=False, na_position="last")
        no_doi = no_doi.drop_duplicates(subset=["Title_key"], keep="first")

        merged = pd.concat([final_doi, no_doi], ignore_index=True)
        merged["Year"] = pd.to_numeric(merged["Year"], errors="coerce").astype("Int64")
        merged["Title_key"] = merged["Title"].apply(normalize_title)

        merged = merged.sort_values(by=["Year"], ascending=False, na_position="last")
        with_doi = merged[merged["DOI"] != ""].drop_duplicates(subset=["DOI"], keep="first")
        without_doi = merged[merged["DOI"] == ""].drop_duplicates(subset=["Title_key"], keep="first")
        merged = pd.concat([with_doi, without_doi], ignore_index=True)

        for col in OUTPUT_COLUMNS:
            if col not in merged.columns:
                merged[col] = ""

        merged = merged[OUTPUT_COLUMNS]

        st.session_state["merged_base"] = merged.copy()

        st.write("Tổng số bản ghi sau ghép:", len(merged))
        st.write("Có DE:", int((merged["DE"] != "").sum()))
        st.write("Có ID:", int((merged["ID"] != "").sum()))
        st.write("Có DE_ID:", int((merged["DE_ID"] != "").sum()))

        st.dataframe(merged.head(15), use_container_width=True)

        st.subheader("Bước 2. Tự động gợi ý các cặp từ gần giống")
        freq_df = extract_keyword_frequency(merged, field="DE_ID")

        s1, s2 = st.columns(2)
        with s1:
            min_count = st.number_input(
                "Số lần xuất hiện tối thiểu",
                min_value=1,
                max_value=20,
                value=2,
                step=1
            )
        with s2:
            similarity_threshold = st.slider(
                "Ngưỡng tương đồng",
                min_value=0.80,
                max_value=0.98,
                value=0.90,
                step=0.01
            )

        suggestion_df = suggest_similar_keywords(
            freq_df,
            min_count=min_count,
            similarity_threshold=similarity_threshold,
            max_suggestions=200
        )

        if suggestion_df.empty:
            st.info("Chưa có gợi ý phù hợp.")
            st.session_state["mapping_editor_df"] = pd.DataFrame(
                columns=["Use", "Original", "Suggested", "Count Original", "Count Suggested", "Similarity"]
            )
        else:
            if st.session_state["mapping_editor_df"].empty:
                st.session_state["mapping_editor_df"] = suggestion_df.copy()
            else:
                # giữ bảng cũ nếu người dùng đã chỉnh, nhưng làm mới khi cấu trúc khác
                expected_cols = ["Use", "Original", "Suggested", "Count Original", "Count Suggested", "Similarity"]
                current_cols = list(st.session_state["mapping_editor_df"].columns)
                if current_cols != expected_cols:
                    st.session_state["mapping_editor_df"] = suggestion_df.copy()

            st.markdown("### Bước 3. Chỉnh sửa bảng mapping rồi bấm Apply")
            edited_df = st.data_editor(
                st.session_state["mapping_editor_df"],
                use_container_width=True,
                num_rows="dynamic",
                key="mapping_editor"
            )

            st.session_state["mapping_editor_df"] = edited_df.copy()

            a1, a2 = st.columns(2)

            with a1:
                if st.button("Apply approved mappings", use_container_width=True):
                    approved_mapping = editor_to_mapping_dict(st.session_state["mapping_editor_df"])
                    st.session_state["approved_mapping"] = approved_mapping

                    merged_final = rebuild_keywords_after_mapping(
                        st.session_state["merged_base"],
                        approved_mapping
                    )
                    st.session_state["merged_final"] = merged_final
                    st.success(f"Đã áp {len(approved_mapping)} mapping đã chọn.")

            with a2:
                if st.button("Reset applied mappings", use_container_width=True):
                    st.session_state["approved_mapping"] = {}
                    st.session_state["merged_final"] = st.session_state["merged_base"].copy()
                    st.success("Đã reset mapping áp dụng.")
st.subheader("Bước 4. Kết quả cuối")

if st.session_state["merged_final"] is None:
    st.session_state["merged_final"] = st.session_state["merged_base"].copy()

merged_final = st.session_state["merged_final"].copy()

st.write("Số mapping đang áp dụng:", len(st.session_state["approved_mapping"]))
st.write("Tổng số bản ghi:", len(merged_final))

st.dataframe(merged_final.head(15), use_container_width=True)

# =========================
# EXPANDER TẢI FILE (GỌN UI)
# =========================
with st.expander("📥 Tải file và hướng dẫn sử dụng", expanded=False):

    st.markdown("### 🧾 Giải thích các file")

    st.markdown("""
**1. Merged đầy đủ (CSV)**  
→ Dữ liệu sau khi ghép ISI + Scopus và đã chuẩn hóa  
→ Dùng để lưu trữ hoặc phân tích tiếp  

**2. File chuẩn cho VOSviewer (CSV)**  
→ Dùng trực tiếp để import vào VOSviewer  
→ Đã chuẩn hóa từ khóa và áp mapping  

**3. Bảng chỉnh sửa mapping (CSV)**  
→ File bạn đã chỉnh trên web  
→ Dùng để chỉnh sửa thêm hoặc lưu lại quá trình làm việc  

**4. Mapping đã duyệt (CSV)**  
→ Danh sách từ khóa đã gộp cuối cùng  
→ Có thể dùng làm thesaurus cho nghiên cứu sau  
""")

    # =========================
    # TẠO FILE
    # =========================
    csv_full = convert_df(merged_final)

    vos_df = create_vosviewer_export(merged_final, keyword_mode=keyword_mode)
    csv_vos = convert_df(vos_df)

    mapping_export_df = st.session_state["mapping_editor_df"].copy()
    csv_mapping = convert_df(mapping_export_df)

    approved_map_df = pd.DataFrame(
        [{"Original": k, "Suggested": v} for k, v in st.session_state["approved_mapping"].items()]
    )
    csv_approved = convert_df(approved_map_df)

    st.markdown("### 📦 Tải file")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.download_button(
            "Merged",
            data=csv_full,
            file_name="merged_data.csv"
        )

    with col2:
        st.download_button(
            "VOSviewer",
            data=csv_vos,
            file_name="vosviewer_ready.csv"
        )

    with col3:
        st.download_button(
            "Mapping table",
            data=csv_mapping,
            file_name="mapping_editor.csv"
        )

    with col4:
        st.download_button(
            "Approved",
            data=csv_approved,
            file_name="approved_mapping.csv"
        )

    # =========================
    # HIỂN THỊ MAPPING NHỎ GỌN
    # =========================
    st.markdown("### 🔎 Mapping đã duyệt")

    if not approved_map_df.empty:
        st.dataframe(approved_map_df, height=200, use_container_width=True)
    else:
        st.caption("Chưa có mapping nào được chọn.")
      
