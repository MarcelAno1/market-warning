
import json
from pathlib import Path

import pandas as pd
import streamlit as st

FILE = Path(__file__).resolve().parent / "latest.json"

st.set_page_config(
    page_title="Market Warning",
    page_icon="📉",
    layout="wide",
)

st.title("🌍 Global Market Warning")
st.caption(
    "Tägliches Frühwarnsystem für Aktienmärkte. "
    "Der Score ist keine Crashwahrscheinlichkeit."
)

if not FILE.exists():
    st.warning(
        "Noch kein Bericht vorhanden. "
        "Führe zuerst `python analyze.py` aus."
    )
    st.stop()

try:
    report = json.loads(FILE.read_text(encoding="utf-8"))
except Exception as exc:
    st.error(f"Bericht kann nicht gelesen werden: {exc}")
    st.stop()

score = float(report["score"])
level = report["level"]

a, b, c = st.columns(3)
a.metric("Risikoscore", f"{score:.1f} / 100")
b.metric("Warnstufe", level)
c.metric("Beobachtete Indizes", len(report.get("markets", [])))

st.progress(max(0.0, min(1.0, score / 100)))

st.subheader("Begründung der Warnstufe")

for reason in report.get("reasons", []):
    st.write("•", reason)

if report.get("missing_components"):
    st.warning(
        "Unvollständige Analyse: " +
        ", ".join(report["missing_components"])
    )

st.subheader("Einzelindikatoren")

component_rows = []

for name, item in report.get("components", {}).items():
    component_rows.append({
        "Indikator": name,
        "Score": item["score"],
        "Gewicht": f"{item['weight'] * 100:.0f} %",
    })

st.dataframe(
    pd.DataFrame(component_rows),
    use_container_width=True,
    hide_index=True,
)

st.subheader("Globale Aktienindizes")

markets = report.get("markets", [])

if markets:
    market_df = pd.DataFrame(markets)
    st.dataframe(
        market_df,
        use_container_width=True,
        hide_index=True,
    )
else:
    st.error("Keine Marktdaten vorhanden.")

st.subheader("VIX")

vix = report.get("vix")

if vix:
    st.json(vix)
else:
    st.warning("VIX-Daten fehlen.")

st.subheader("Nachrichten")

news = report.get("news", [])

if news:
    for article in news:
        title = article.get("title", "Ohne Titel")
        url = article.get("url", "")
        source = article.get("source", "Quelle unbekannt")

        if url:
            st.markdown(f"- [{title}]({url})")
        else:
            st.write("-", title)

        st.caption(
            f"Quelle: {source} | "
            f"Risikobegriffe: {article.get('risk_hits', 0)}"
        )
else:
    st.info("Keine Nachrichten verfügbar.")

st.subheader("Datenqualität")

st.write("Erstellt (UTC):", report.get("generated_at"))
st.write("Methode:", report.get("method"))

if report.get("data_errors"):
    with st.expander("Fehler beim Datenabruf"):
        for error in report["data_errors"]:
            st.write("-", error)

if report.get("news_error"):
    st.warning("Nachrichtenfehler: " + report["news_error"])

st.divider()
st.caption(
    "Informationssystem, keine Anlageberatung. "
    "Keine automatischen Kauf- oder Verkaufsentscheidungen."
)
