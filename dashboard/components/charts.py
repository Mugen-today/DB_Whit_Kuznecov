"""Графические сводки заболеваемости."""

import pandas as pd
import streamlit as st


def render(records, *args, **kwargs):
    st.subheader("Статистические графики и распределения")
    if not records:
        st.info("Нет записей для построения графиков по выбранным фильтрам.")
        return

    df = pd.DataFrame(records)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### Ведущие диагнозы")
        top_diag = df["diagnosis"].replace("", pd.NA).dropna().value_counts().head(10)
        st.bar_chart(top_diag, color="#2563eb")

    with col2:
        st.markdown("##### Распределение по тяжести течения")
        sev_counts = df["severity"].replace("", pd.NA).dropna().value_counts()
        st.bar_chart(sev_counts, color="#dc2626")

    col3, col4 = st.columns(2)
    with col3:
        st.markdown("##### Динамика обращений по датам")
        valid_dates = df[df["date"].astype(str).str.len() >= 10]
        if not valid_dates.empty:
            date_series = valid_dates.groupby("date").size()
            st.line_chart(date_series, color="#059669")
        else:
            st.caption("Недостаточно данных о датах.")

    with col4:
        st.markdown("##### Социальные категории пациентов")
        soc_counts = df["social_group"].replace("", pd.NA).dropna().value_counts().head(10)
        st.bar_chart(soc_counts, color="#7c3aed")

    col5, col6 = st.columns(2)
    with col5:
        st.markdown("##### Распределение по районам")
        mun_counts = df["municipality"].replace("", pd.NA).dropna().value_counts().head(10)
        st.bar_chart(mun_counts, color="#d97706")

    with col6:
        st.markdown("##### Исходы лечения и наблюдения")
        outcome_counts = df["outcome"].replace("", pd.NA).dropna().value_counts().head(8)
        st.bar_chart(outcome_counts, color="#0284c7")