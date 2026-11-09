"""Data filters component for GIS-MongoDB Dashboard."""

import streamlit as st


def render(records, *args, **kwargs):
  st.sidebar.markdown("### 🔎 Фильтрация данных")

  if not records:
    st.sidebar.info("База данных пока пуста. Загрузите исходный файл командой импорта.")
    return []

  all_regions = sorted({r.get("region", "Не указан") for r in records})
  selected_regions = st.sidebar.multiselect(
      "Регион (Region)", options=all_regions, default=all_regions
  )

  all_severities = sorted({r.get("severity", "Средняя") for r in records})
  selected_severities = st.sidebar.multiselect(
      "Степень тяжести (Severity)",
      options=all_severities,
      default=all_severities,
  )

  ages = [
      r.get("age")
      for r in records
      if isinstance(r.get("age"), int)
  ]
  min_age, max_age = (min(ages), max(ages)) if ages else (0, 100)
  if min_age == max_age:
    min_age, max_age = 0, 100
  age_range = st.sidebar.slider(
      "Возраст пациента (Patient.age)",
      min_value=0,
      max_value=max(100, max_age),
      value=(min_age, max_age),
  )

  only_hosp = st.sidebar.checkbox("Только с госпитализацией", value=False)
  only_relapse = st.sidebar.checkbox("Только рецидивы", value=False)

  filtered = []
  for r in records:
    if r.get("region", "Не указан") not in selected_regions:
      continue
    if r.get("severity", "Средняя") not in selected_severities:
      continue
    age = r.get("age")
    if isinstance(age, int) and not (age_range[0] <= age <= age_range[1]):
      continue
    if only_hosp and not r.get("hospitalized"):
      continue
    if only_relapse and not r.get("relapse"):
      continue
    filtered.append(r)

  st.sidebar.caption(f"Отобрано записей: **{len(filtered)}** из {len(records)}")
  return filtered