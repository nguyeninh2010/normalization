import streamlit as st
import pandas as pd
import re
from io import BytesIO
from difflib import SequenceMatcher

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="Keyword Cleaner", layout="wide")

# =========================
# BASIC CLEAN
# =========================
def clean_text(x):
    if pd.isna(x):
        return ""
    x = str(x).strip().lower()
    x = re.sub(r"\s+", " ", x)
    return x

def normalize_keywords(text):
    if not text:
        return ""
    text = text.replace(",", ";")
    parts = [clean_text(p) for p in text.split(";") if p.strip()]
    return "; ".join(sorted(set(parts)))

# =========================
# KEYWORD MERGE
# =========================
def merge_keywords(de, id_):
    return normalize_keywords(de + ";" + id_)

# =========================
# FILE EXPORT
# =========================
def to_csv_bytes(df):
    buffer = BytesIO()
    df.to_csv(buffer, index=False, encoding="utf-8-sig")
    return buffer.getvalue()

# =========================
# SIMILARITY (OPTIMIZED)
# =========================
def suggest_keywords(df, min_count=2, threshold=0.9, max_terms=300):
    keywords = []

    for val in df["DE_ID"]:
        if val:
            keywords += val.split(";")

    freq = pd.Series(keywords).value_counts()
    freq = freq[freq >= min_count]

    # LIMIT để tránh O(n^2) quá lớn
    terms = freq.index.tolist()[:max_terms]

    rows = []

    for i in range(len(terms)):
        for j in range(i + 1, len(terms)):
            k1 = terms[i]
            k2 = terms[j]

            sim = SequenceMatcher(None, k1, k2).ratio()

            if sim >= threshold:
                rows.append({
                    "Use": False,
                    "Original": k2,
                    "Suggested": k1,
                    "Similarity": round(sim, 3)
                })

    return pd.DataFrame(rows)

# =========================
# APPLY MAPPING
# =========================
def apply_mapping(df, mapping):
    def replace_func(text):
        if not text:
            return ""
        parts = text.split(";")
        new = []
        for p in parts:
            p = p.strip()
            p = mapping.get(p, p)
            new.append(p)
        return "; ".join(sorted(set(new)))

    df = df.copy()
    df["DE"] = df["DE"].apply(replace_func)
    df["ID"] = df["ID"].apply(replace_func)
    df["DE_ID"] = df.apply(lambda r: merge_keywords(r["DE"], r["ID"]), axis=1)

    return df

# =========================
# SESSION
# =========================
if "data" not in st.session_state:
    st.session_state.data = None

if "suggest" not in st.session_state:
    st.session_state.suggest = None

if "mapping" not in st.session_state:
    st.session_state.mapping = {}

if "final" not in st.session_state:
    st.session_state.final = None

# =========================
# UI
# =========================
st.title("📘 Keyword Normalization Tool")

# =========================
# STEP 1 UPLOAD
# =========================
st.header("1. Upload data")

file = st.file_uploader("Upload CSV (Scopus/ISI merged)", type=["csv"])

if file:
    df = pd.read_csv(file)

    df["DE"] = df.get("DE", "")
    df["ID"] = df.get("ID", "")

    df["DE"] = df["DE"].apply(normalize_keywords)
    df["ID"] = df["ID"].apply(normalize_keywords)

    df["DE_ID"] = df.apply(lambda r: merge_keywords(r["DE"], r["ID"]), axis=1)

    st.session_state.data = df

    st.success("Loaded!")
    st.dataframe(df.head(10))

# =========================
# STEP 2 SUGGEST
# =========================
if st.session_state.data is not None:

    st.header("2. Generate keyword suggestions")

    col1, col2 = st.columns(2)

    with col1:
        min_count = st.number_input("Min occurrence", 1, 10, 2)

    with col2:
        threshold = st.slider("Similarity", 0.8, 0.98, 0.9)

    if st.button("Generate suggestions"):
        with st.spinner("Processing..."):
            st.session_state.suggest = suggest_keywords(
                st.session_state.data,
                min_count=min_count,
                threshold=threshold
            )

    if st.session_state.suggest is not None:
        st.dataframe(st.session_state.suggest, height=300)

# =========================
# STEP 3 EDIT + APPLY
# =========================
if st.session_state.suggest is not None:

    st.header("3. Edit mapping")

    edited = st.data_editor(
        st.session_state.suggest,
        num_rows="dynamic",
        use_container_width=True
    )

    if st.button("Apply mapping"):
        mapping = {}

        for _, row in edited.iterrows():
            if row["Use"]:
                mapping[row["Original"]] = row["Suggested"]

        st.session_state.mapping = mapping
        st.session_state.final = apply_mapping(st.session_state.data, mapping)

        st.success(f"Applied {len(mapping)} mappings")

# =========================
# STEP 4 RESULT + DOWNLOAD
# =========================
if st.session_state.final is not None:

    st.header("4. Result")

    st.dataframe(st.session_state.final.head(15))

    with st.expander("📥 Download & usage guide"):

        st.markdown("""
### File explanation

**Merged file**
→ full dataset for analysis  

**VOSviewer file**
→ use for visualization  

**Mapping table**
→ editable mapping  

**Approved mapping**
→ final thesaurus  
""")

        merged_csv = to_csv_bytes(st.session_state.final)

        vos = st.session_state.final.copy()
        vos["Author Keywords"] = vos["DE_ID"]
        vos_csv = to_csv_bytes(vos)

        mapping_df = pd.DataFrame([
            {"Original": k, "Suggested": v}
            for k, v in st.session_state.mapping.items()
        ])

        mapping_csv = to_csv_bytes(mapping_df)

        col1, col2, col3 = st.columns(3)

        with col1:
            st.download_button("Merged", merged_csv, "merged.csv")

        with col2:
            st.download_button("VOSviewer", vos_csv, "vosviewer.csv")

        with col3:
            st.download_button("Mapping", mapping_csv, "mapping.csv")
