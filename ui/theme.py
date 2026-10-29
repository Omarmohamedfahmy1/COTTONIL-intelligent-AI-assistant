"""Navy/Teal shell, local Arabic-capable fonts, numeric/plot direction isolation."""
import streamlit as st


def apply_theme(lang):
    direction='ltr' if lang=='English' else 'rtl'
    align='left' if lang=='English' else 'right'
    st.markdown(f'''<style>
    html, body, [data-testid="stApp"] {{font-family: "Segoe UI", Tahoma, Arial, sans-serif;}}
    .stApp {{background:#f4f7fa;color:#10263e;}}
    [data-testid="stMainBlockContainer"] {{max-width:1600px;padding-top:2rem;padding-bottom:2rem;direction:{direction};text-align:{align};}}
    [data-testid="stSidebar"] {{background:#10263e;direction:{direction};text-align:{align};min-width:285px;}}
    [data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3,[data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label,[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{color:#ecf4fa;}}
    [data-testid="stSidebar"] input,[data-testid="stSidebar"] [data-baseweb="select"] * {{color:#10263e;}}
    [data-testid="stSidebar"] [role="radiogroup"] {{gap:.55rem;}}
    [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {{background:#1c4a60;border-radius:8px;}}
    [data-testid="stHorizontalBlock"] {{direction:{direction};}}
    [data-testid="stMetric"] {{background:white;border:1px solid #e0e8ee;border-top:3px solid #0c9697;border-radius:12px;padding:1rem 1.15rem;min-height:120px;}}
    [data-testid="stMetricLabel"] {{font-weight:600;color:#53697b;}}
    [data-testid="stMetricValue"] {{color:#10263e;font-size:1.8rem;direction:{direction};text-align:{align};font-variant-numeric:tabular-nums;white-space:normal;overflow-wrap:anywhere;}}
    [data-testid="stHeading"] h1,[data-testid="stCaptionContainer"],
    [data-testid="stMarkdownContainer"] {{direction:{direction};text-align:{align};}}
    button [data-testid="stMarkdownContainer"] {{text-align:center;}}
    [data-testid="stHeading"] a {{display:none;}}
    [data-testid="stDateInput"] {{direction:ltr;text-align:{align};}}
    [data-testid="stDateInput"] label {{direction:{direction};}}
    h1,h2,h3 {{color:#10263e;letter-spacing:normal;}}
    [data-testid="stHeading"] h1 {{font-size:2rem !important;}} h2 {{font-size:1.35rem;}}
    .stButton button,.stDownloadButton button {{border-radius:8px;min-height:2.5rem;}}
    [data-testid="stChatMessage"] {{background:white;border:1px solid #dfe8ef;border-radius:12px;direction:{direction};text-align:{align};}}
    [class*="st-key-assistant_en_"] [data-testid="stMarkdownContainer"],
    [class*="st-key-assistant_en_"] [data-testid="stCaptionContainer"] {{direction:ltr;text-align:left;}}
    [class*="st-key-assistant_ar_"] [data-testid="stMarkdownContainer"],
    [class*="st-key-assistant_ar_"] [data-testid="stCaptionContainer"] {{direction:rtl;text-align:right;}}
    [data-testid="stDialog"] {{direction:{direction};text-align:{align};}}
    .js-plotly-plot {{direction:ltr;text-align:left;}}
    [data-testid="stDataFrame"] {{direction:ltr;}}
    input {{font-variant-numeric:tabular-nums;}}
    [data-testid="stElementToolbar"],[data-testid="stAppDeployButton"],#MainMenu {{display:none;}}
    @media(max-width:800px) {{[data-testid="stHorizontalBlock"] {{flex-wrap:wrap;}} [data-testid="stColumn"] {{min-width:240px;}} [data-testid="stHeading"] h1 {{font-size:1.55rem !important;}}}}
    </style>''',unsafe_allow_html=True)
