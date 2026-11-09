"""Statistical charts component for GIS-MongoDB Dashboard."""

import pandas as pd
import streamlit as st


def render(records, *args, **kwargs):
  st.subheader("📊 Аналитика по пациентам и терапии (Patient & Therapy)")

  if not records:
    st.info("Нет данных для построения графиков.")
    return

  df = pd.DataFrame(records)

  col1, col2 = st.columns(2)

  with col1:
    st.markdown("**Распределение по диагнозам (Therapy.diagnosis)**")
    diag_counts = df["diagnosis"].value_counts()
    st.bar_chart(diag_counts, color="#3b82f6")

  with col2:
    st.markdown("**Степень тяжести случаев (Severity.degree)**")
    sev_counts = df["severity"].value_counts()
    st.bar_chart(sev_counts, color="#ef4444")

  col3, col4 = st.columns(2)

  with col3:
    st.markdown("**Динамика обращений по датам (Instances.date)**")
    date_counts = df.groupby("date").size()
    st.line_chart(date_counts, color="#10b981")

  with col4:
    st.markdown("**Социальные группы пациентов (Social_group.type)**")
    soc_counts = df["social_group"].value_counts()
    st.bar_chart(soc_counts, color="#8b5cf6")