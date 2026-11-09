"""Map display component for GIS-MongoDB Dashboard."""

import pandas as pd
import pydeck as pdk
import streamlit as st

SEVERITY_COLORS = {
    "Легкая": [46, 204, 113, 200],      # Зеленый
    "Средняя": [241, 196, 15, 200],     # Желтый
    "Тяжелая": [230, 126, 34, 215],     # Оранжевый
    "Критическая": [231, 76, 60, 235],  # Красный
}


def render(records, *args, **kwargs):
  st.subheader("🗺️ Пространственное распределение очагов (Foci & Geodata)")

  geo_records = [
      r
      for r in records
      if r.get("lat") is not None and r.get("lon") is not None
  ]
  if not geo_records:
    st.info("Нет геопривязанных записей для отображения на карте.")
    return

  df = pd.DataFrame(geo_records)
  df["color"] = df.get("severity", pd.Series("Не указана", index=df.index)).map(
      lambda s: SEVERITY_COLORS.get(s, [52, 152, 219, 200])
  )
  df["radius"] = df.get("severity", pd.Series("Не указана", index=df.index)).map(
      lambda s: 900
      if s == "Критическая"
      else (650 if s == "Тяжелая" else 450)
  )

  mid_lat = float(df["lat"].mean())
  mid_lon = float(df["lon"].mean())

  layer = pdk.Layer(
      "ScatterplotLayer",
      data=df,
      get_position="[lon, lat]",
      get_fill_color="color",
      get_radius="radius",
      pickable=True,
      opacity=0.85,
      stroked=True,
      filled=True,
      radius_min_pixels=6,
      radius_max_pixels=22,
  )

  view_state = pdk.ViewState(
      latitude=mid_lat,
      longitude=mid_lon,
      zoom=8.5,
      pitch=25,
  )

  tooltip = {
      "text": (
          "Населенный пункт: {settlement} ({region})\n"
          "Улица: {street}, д. {house}\n"
          "Диагноз: {diagnosis}\n"
          "Тяжесть: {severity}\n"
          "Возраст пациента: {age} лет\n"
          "Высота (Elevation): {elevation} м"
      ),
      "style": {
          "backgroundColor": "#1e293b",
          "color": "white",
          "fontSize": "13px",
      },
  }

  st.pydeck_chart(
      pdk.Deck(
          layers=[layer],
          initial_view_state=view_state,
          tooltip=tooltip,
      )
  )

  st.caption(
      "🟢 Легкая  |  🟡 Средняя  |  🟠 Тяжелая  |  🔴 Критическая "
      "(Наведите курсор на точку очага для просмотра карточки локации)"
  )