"""Интерактивная карта очагов с поддержкой кластеризации до 100 000 записей."""

import math
import html
import pandas as pd
import pydeck as pdk
import streamlit as st

SEVERITY_COLORS = {
    "Легкая": [46, 204, 113, 200],
    "Средняя": [241, 196, 15, 215],
    "Тяжелая": [231, 76, 60, 235],
    "Критическая": [192, 57, 43, 245],
}


def render(records, *args, **kwargs):
    geo_records = [
        {
            "lat": float(r["lat"]),
            "lon": float(r["lon"]),
            "diagnosis": html.escape(str(r.get("diagnosis", ""))),
            "severity": html.escape(str(r.get("severity", "Не указана"))),
            "address": html.escape(str(r.get("address", ""))),
            "date": html.escape(str(r.get("date", ""))),
            "age_display": f"{int(r['age'])} лет" if isinstance(r.get("age"), (int, float)) else "Не указан",
            "hospital": html.escape(str(r.get("hospital", ""))),
            "outcome": html.escape(str(r.get("outcome", ""))),
        }
        for r in records
        if isinstance(r.get("lat"), (int, float)) and isinstance(r.get("lon"), (int, float))
        and math.isfinite(float(r["lat"])) and math.isfinite(float(r["lon"]))
        and -90 <= float(r["lat"]) <= 90 and -180 <= float(r["lon"]) <= 180
    ]

    if not geo_records:
        st.info("По заданным условиям фильтрации нет очагов с координатами на карте.")
        return

    total_geo = len(geo_records)

    col_m1, col_m2 = st.columns([2, 2])
    with col_m1:
        default_idx = 0 if total_geo > 2000 else 1
        map_mode = st.radio(
            "Режим отображения на карте",
            ["Кластеры плотности очагов", "Отдельные точки обращений"],
            index=default_idx,
            horizontal=True,
        )
    with col_m2:
        if map_mode == "Кластеры плотности очагов":
            cluster_radius = st.slider("Радиус объединения кластера, м", 200, 3000, 800, step=200)
        else:
            max_pts = st.slider("Лимит отдельных точек на экране", 1000, 20000, 5000, step=1000)

    df = pd.DataFrame(geo_records)
    mid_lat = float(df["lat"].mean())
    mid_lon = float(df["lon"].mean())

    if map_mode == "Кластеры плотности очагов":
        # В режиме кластеров агрегируются абсолютно все записи (до 100 000+) без нагрузки на браузер
        layer = pdk.Layer(
            "HexagonLayer",
            data=df[["lon", "lat"]],
            get_position="[lon, lat]",
            radius=cluster_radius,
            elevation_scale=15,
            elevation_range=[0, 1000],
            pickable=True,
            extruded=True,
            coverage=0.88,
            color_range=[
                [46, 204, 113, 180],
                [163, 228, 215, 195],
                [241, 196, 15, 210],
                [243, 156, 18, 225],
                [231, 76, 60, 240],
                [192, 57, 43, 255],
            ],
        )
        view_state = pdk.ViewState(latitude=mid_lat, longitude=mid_lon, zoom=8.5, pitch=35)
        tooltip = {
            "html": "<b>Количество случаев в кластере:</b> {elevationValue}",
            "style": {"backgroundColor": "#0f172a", "color": "white", "fontSize": "13px", "padding": "8px"},
        }
        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip))
        st.caption(
            f"На карте сгруппированы все {total_geo} записей. "
            "Цвет и высота ячейки отражают концентрацию заболевших в данном секторе."
        )
    else:
        if total_geo > max_pts:
            st.caption(
                f"Отображено {max_pts} точек из {total_geo}. "
                "Для просмотра всех записей сразу переключитесь в режим кластеров плотности."
            )
            step = max(1, total_geo // max_pts)
            df = df.iloc[::step].head(max_pts).copy()

        df["color"] = df["severity"].map(lambda s: SEVERITY_COLORS.get(s, [52, 152, 219, 200]))
        df["radius"] = df["severity"].map(
            lambda s: 250 if s in ("Тяжелая", "Критическая") else (170 if s == "Средняя" else 110)
        )

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
            radius_min_pixels=4,
            radius_max_pixels=12,
        )
        view_state = pdk.ViewState(latitude=mid_lat, longitude=mid_lon, zoom=8.5, pitch=0)
        tooltip = {
            "html": (
                "<b>Диагноз:</b> {diagnosis}<br/>"
                "<b>Тяжесть:</b> {severity}<br/>"
                "<b>Адрес:</b> {address}<br/>"
                "<b>Дата:</b> {date} | <b>Возраст:</b> {age_display}<br/>"
                "<b>Учреждение:</b> {hospital}<br/>"
                "<b>Исход:</b> {outcome}"
            ),
            "style": {"backgroundColor": "#0f172a", "color": "white", "fontSize": "12px", "padding": "8px"},
        }
        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip))
        st.caption("Зеленый — легкая степень | Желтый — средняя степень | Красный — тяжелая степень")
