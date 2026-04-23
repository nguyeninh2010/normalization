import streamlit as st
import pandas as pd
import bibtexparser
from io import BytesIO
import re
from difflib import SequenceMatcher

# =========================
# CONFIG
# =========================
OUTPUT_COLUMNS = [
    "Title","Authors","Author full names","Affiliations",
    "DE","ID","DE_ID","Keyword_Source",
    "References","DOI","Year","Source title",
    "Volume","Issue","Page start","Page end"
]

# =========================
# CLEAN
# =========================
def clean_text(x):
    if pd.isna(x):
        return ""
    x = str(x).strip().lower()
    x = re.sub(r"\s+"," ",x)
    return x

def clean_doi(x):
    x = clean_text(x)
    x = x.replace("https://doi.org/","").replace("doi:","")
    return x

def normalize_keywords(text):
    if not text:
        return ""
    text = text.replace(",", ";")
    parts = [clean_text(p) for p in text.split(";") if p.strip()]
    return "; ".join(sorted(set(parts)))

def merge_kw(de,id_):
    return normalize_keywords(de+";"+id_)

def detect_source(de,id_):
    if de and id_:
        return "DE+ID"
    if de:
        return "DE"
    if id_:
        return "ID"
    return "None"

# =========================
# READ FILE
# =========================
def read_file(file):
    ext = file.name.split(".")[-1]
    if ext=="bib":
        bib = bibtexparser.load(file)
        rows=[]
        for e in bib.entries:
            rows.append({
                "Title":e.get("title",""),
                "Authors":e.get("author",""),
                "DE":e.get("keywords",""),
                "ID":e.get("keywords-plus",""),
                "DOI":e.get("doi",""),
                "Year":e.get("year","")
            })
        return pd.DataFrame(rows)
    elif ext=="csv":
        return pd.read_csv(file)
    else:
        return pd.read_excel(file)

# =========================
# STANDARDIZE
# =========================
def standardize(df):
    df = df.copy()

    df["DOI"] = df.get("DOI","").apply(clean_doi)
    df["Title"] = df.get("Title","").apply(clean_text)
    df["Year"] = pd.to_numeric(df.get("Year",""),errors="coerce")

    df["DE"] = df.get("DE","").apply(normalize_keywords)
    df["ID"] = df.get("ID","").apply(normalize_keywords)

    df["DE_ID"] = df.apply(lambda r: merge_kw(r["DE"],r["ID"]),axis=1)
    df["Keyword_Source"] = df.apply(lambda r: detect_source(r["DE"],r["ID"]),axis=1)

    return df

# =========================
# MERGE DOI
# =========================
def merge_data(df1,df2):
    m = pd.merge(df1,df2,on="DOI",how="outer",suffixes=("_1","_2"))

    out = pd.DataFrame()
    out["DOI"]=m["DOI"]

    for col in ["Title","Authors","Year"]:
        c1=col+"_1"
        c2=col+"_2"
        if c1 in m and c2 in m:
            out[col]=m[c1].combine_first(m[c2])
        elif c1 in m:
            out[col]=m[c1]
        else:
            out[col]=m[c2]

    out["DE"]=m.apply(lambda r: merge_kw(r.get("DE_1",""),r.get("DE_2","")),axis=1)
    out["ID"]=m.apply(lambda r: merge_kw(r.get("ID_1",""),r.get("ID_2","")),axis=1)
    out["DE_ID"]=out.apply(lambda r: merge_kw(r["DE"],r["ID"]),axis=1)

    return out

# =========================
# SUGGEST
# =========================
def suggest(df,min_count=2,threshold=0.9,max_terms=300):
    kws=[]
    for v in df["DE_ID"]:
        if v:
            kws+=v.split(";")

    freq=pd.Series(kws).value_counts()
    freq=freq[freq>=min_count]

    terms=freq.index[:max_terms]

    rows=[]
    for i in range(len(terms)):
        for j in range(i+1,len(terms)):
            s=SequenceMatcher(None,terms[i],terms[j]).ratio()
            if s>=threshold:
                rows.append({
                    "Use":False,
                    "Original":terms[j],
                    "Suggested":terms[i],
                    "Similarity":round(s,3)
                })
    return pd.DataFrame(rows)

# =========================
# APPLY
# =========================
def apply_map(df,map_):
    def f(text):
        if not text:
            return ""
        parts=text.split(";")
        new=[map_.get(p.strip(),p.strip()) for p in parts]
        return "; ".join(sorted(set(new)))
    df=df.copy()
    df["DE"]=df["DE"].apply(f)
    df["ID"]=df["ID"].apply(f)
    df["DE_ID"]=df.apply(lambda r: merge_kw(r["DE"],r["ID"]),axis=1)
    return df

# =========================
# EXPORT
# =========================
def to_csv(df):
    b=BytesIO()
    df.to_csv(b,index=False,encoding="utf-8-sig")
    return b.getvalue()

# =========================
# UI
# =========================
st.set_page_config(layout="wide")
st.title("📘 ISI + Scopus Keyword Tool")

# =========================
# UPLOAD
# =========================
isi = st.file_uploader("ISI file",type=["bib","csv","xlsx"])
scopus = st.file_uploader("Scopus file",type=["csv","xlsx"])

if isi and scopus:

    df1 = standardize(read_file(isi))
    df2 = standardize(read_file(scopus))

    merged = merge_data(df1,df2)

    st.session_state["base"]=merged

    st.success("Merged done")
    st.dataframe(merged.head(10))

# =========================
# SUGGEST
# =========================
if "base" in st.session_state:

    st.header("Suggest keywords")

    if st.button("Generate"):
        st.session_state["suggest"]=suggest(st.session_state["base"])

    if "suggest" in st.session_state:
        edit = st.data_editor(st.session_state["suggest"],use_container_width=True)

        if st.button("Apply"):
            mp={}
            for _,r in edit.iterrows():
                if r["Use"]:
                    mp[r["Original"]]=r["Suggested"]

            st.session_state["map"]=mp
            st.session_state["final"]=apply_map(st.session_state["base"],mp)

# =========================
# STEP 4 UI GỌN
# =========================
if "final" in st.session_state:

    st.subheader("Kết quả cuối")
    final = st.session_state["final"]

    st.dataframe(final.head(10))

    with st.expander("📥 Tải file và hướng dẫn"):

        st.markdown("""
**Merged:** dữ liệu đầy đủ  
**VOSviewer:** dùng vẽ bản đồ  
**Mapping:** bảng chỉnh sửa  
**Approved:** mapping cuối  
""")

        csv1 = to_csv(final)

        vos = final.copy()
        vos["Author Keywords"]=vos["DE_ID"]
        csv2 = to_csv(vos)

        map_df = pd.DataFrame([
            {"Original":k,"Suggested":v}
            for k,v in st.session_state.get("map",{}).items()
        ])
        csv3 = to_csv(map_df)

        c1,c2,c3 = st.columns(3)

        with c1:
            st.download_button("Merged",csv1,"merged.csv")
        with c2:
            st.download_button("VOS",csv2,"vos.csv")
        with c3:
            st.download_button("Mapping",csv3,"mapping.csv")
