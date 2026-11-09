"""User-Friendly Medical GIS Dashboard (Team Lead 17-Collection Schema + TZ Queries)."""

import json
import os
import urllib.parse
import urllib.request
import xml.sax.saxutils as saxutils
from functools import wraps

import pandas as pd
import streamlit as st

from components import charts, filters, maps

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000").rstrip("/")


def api_get(path):
    req = urllib.request.Request(f"{BACKEND_URL}{path}", method="GET")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def show_api_error(function):
    """Keep failed button requests readable without exposing a Python traceback."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception as exc:
            st.error(f"Запрос не выполнен: {exc}. Проверьте backend и повторите действие.")
            st.stop()
    return wrapped

@show_api_error

def api_post_json(path, payload=None, raw_text=None, content_type="application/json"):
    data = raw_text.encode("utf-8") if raw_text is not None else json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        f"{BACKEND_URL}{path}",
        data=data,
        headers={"Content-Type": content_type},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


@show_api_error
def api_upload_gpkg(file_bytes, filename):
    safe_filename = urllib.parse.quote(filename)
    req = urllib.request.Request(
        f"{BACKEND_URL}/v1/import-gpkg",
        data=file_bytes,
        headers={"Content-Type": "application/octet-stream", "X-Filename": safe_filename},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    st.set_page_config(page_title="ЭпидМониторинг СПб и ЛО", page_icon="🏥", layout="wide")

    st.title("🏥 Система эпидемиологического мониторинга СПб и Ленинградской области")
    st.caption(
        "Рабочее место врача-эпидемиолога | Хранилище: 17 нормализованных коллекций `Schema` + приёмник `cases`"
    )

    st.sidebar.markdown("### 🔐 Режим входа в систему")
    role_choice = st.sidebar.selectbox(
        "Выберите права доступа:",
        [
            ("reader", "Главврач / Аналитик (Полный доступ)"),
            ("user", "Дежурный врач (Оператор отделения)"),
            ("guest", "Внешний исследователь (Гость — адреса скрыты)"),
        ],
        format_func=lambda x: x[1],
    )
    selected_role = role_choice[0]

    try:
        overview = api_get(f"/v1/overview?role={selected_role}")
    except Exception as exc:
        st.error(f"Нет связи с сервером базы данных ({BACKEND_URL}). Детали: {exc}")
        st.stop()

    if st.sidebar.button("Обновить данные"):
        st.rerun()
    try:
        stats = api_get("/v1/statistics")
    except Exception as exc:
        st.error(f"Не удалось получить общую статистику: {exc}")
        st.stop()
    st.subheader("Вся база данных — точные количества")
    columns = st.columns(5)
    for column, name in zip(columns, ("Patient", "Instances", "Therapy", "Foci", "Geodata")):
        column.metric(name, stats["counts"][name])
    with st.expander("Общая динамика и возраст пациентов", expanded=True):
        if stats["dates"]:
            st.line_chart(pd.DataFrame(stats["dates"]).set_index("_id")["count"])
        if stats["ages"]:
            age_frame = pd.DataFrame(stats["ages"])
            age_frame["_id"] = age_frame["_id"].map(lambda x: "Не указан" if pd.isna(x) else str(int(x)))
            st.bar_chart(age_frame.set_index("_id")["count"])
    with st.expander("Координаты Geodata (независимо от медицинских связей)", expanded=True):
        st.caption(f"Показано {stats['map_shown']} точек, максимум {stats['map_limit']}. "
                   "Это координаты, а не подтверждённые очаги. Фильтры журнала на эту карту не действуют.")
        maps.render(stats["points"])
    st.info("Журнал ниже ограничен последними 2500 обращениями. Его фильтры и показатели относятся только к выборке. "
            "Отсутствующие связи с Therapy/Foci не восстанавливаются по номеру строки.")
    records = overview.get("records", [])
    counts = overview.get("counts", {})
    total_in_cases = overview.get("total_in_cases", 0)
    total_instances = overview.get("total_instances", 0)
    sample_5 = overview.get("sample_5_docs", [])

    filtered_records = filters.render(records)

    covid_cnt = sum(1 for r in filtered_records if "COVID" in r.get("source", ""))
    tb_cnt = sum(1 for r in filtered_records if "Туберкулёз" in r.get("source", ""))
    hosp_cnt = sum(1 for r in filtered_records if r.get("hospitalized"))

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("📦 В буфере cases", max(0, total_in_cases))
    c2.metric("🗂️ В схеме (Instances)", max(0, total_instances))
    c3.metric("🦠 COVID-19 и ОРВИ", covid_cnt)
    c4.metric("🫁 Туберкулёз (ЛО)", tb_cnt)
    c5.metric("🏥 Госпитализировано", hosp_cnt)

    st.markdown("---")

    tab_main, tab_queries, tab_upload, tab_qgis = st.tabs([
        "🗺️ Карта очагов и Журнал пациентов",
        "🔎 Эпидемиологический анализ (6 запросов ТЗ + JSON/XML)",
        "📥 Загрузка геопакетов (.gpkg) и 17 коллекций",
        "🛰️ Синхронизация с QGIS и Конструктор",
    ])

    with tab_main:
        if not filtered_records:
            st.warning(
                "База данных пока пуста или случаи скрыты фильтром. "
                "Перейдите на вкладку **«📥 Загрузка геопакетов (.gpkg) и 17 коллекций»** и загрузите ваши файлы `.gpkg`!"
            )
        else:
            if selected_role == "guest":
                st.info(
                    "🔒 Вы вошли как **Гость**: сервер MongoDB автоматически засекретил улицы, номера домов и соц. группы."
                )
            maps.render(filtered_records)
            st.markdown("---")
            charts.render(filtered_records)
            st.markdown("---")
            st.subheader("📋 Сводный медицинский журнал обращений (собран из 17 коллекций схемы)")
            df_display = pd.DataFrame(filtered_records).rename(columns={
                "source": "Источник данных",
                "date": "Дата",
                "age": "Возраст",
                "region": "Территория",
                "address": "Адрес очага (Location)",
                "diagnosis": "Диагноз (Therapy)",
                "severity": "Тяжесть (Severity)",
                "social_group": "Соц. группа",
                "hospital": "Медучреждение / Режим ХТ",
                "outcome": "Исход",
                "symptoms": "Симптомы / Препараты устойчивости",
            })
            cols_to_show = [
                "Дата", "Источник данных", "Диагноз (Therapy)", "Тяжесть (Severity)",
                "Возраст", "Территория", "Адрес очага (Location)",
                "Соц. группа", "Медучреждение / Режим ХТ", "Симптомы / Препараты устойчивости", "Исход",
            ]
            st.dataframe(
                df_display[[c for c in cols_to_show if c in df_display.columns]],
                width="stretch",
                hide_index=True,
            )

    with tab_queries:
        st.subheader("🔎 Типовые запросы врача-эпидемиолога (по ТЗ и архитектуре тимлида)")
        q_choice = st.radio(
            "Выберите вид эпидемиологического запроса:",
            [
                ("q1_polygon", "📍 1. Найти все случаи внутри выбранного района (Василеостровский р-н СПб, Всеволожский и др.)"),
                ("q2_nearest", "🏠 2. Найти 100 ближайших случаев к заданному адресу / координатам проживания"),
                ("q3_periods", "📆 3. Сравнить случаи внутри района за 2 разных периода времени (с ... по ...)"),
                ("q4_timeseries", "📈 4. Сгруппировать случаи по датам и вывести динамику заболеваемости (временной ряд)"),
                ("q5_group_age", "👥 5. Сгруппировать случаи по признаку и рассчитать количество и средний возраст"),
                ("q6_unwind", "💊 6. Развернуть массивы ($unwind) и вывести Топ-5 частых симптомов и препаратов устойчивости"),
            ],
            format_func=lambda x: x[1],
        )[0]

        payload = {"query_type": q_choice, "role": selected_role}

        if q_choice == "q1_polygon":
            payload["district"] = st.selectbox(
                "Выберите район Санкт-Петербурга или Ленинградской области:",
                [
                    "Василеостровский район (СПб)",
                    "Центральный и Адмиралтейский р-ны (СПб)",
                    "Всеволожский район (Мурино / Кудрово / Бугры)",
                    "Бокситогорский район (Пикалёво / Бор / Ефимовский)",
                    "Волховский район (Сясьстрой / Новая Ладога / Паша)",
                    "Волосовский район (Бегуницы / Извара / Кикерино)",
                ],
            )

        elif q_choice == "q2_nearest":
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                preset = st.selectbox(
                    "Ориентир (или введите координаты вручную):",
                    [
                        ("Василеостровская (СПб)", 59.9426, 30.2783),
                        ("Площадь Восстания (СПб)", 59.9311, 30.3609),
                        ("г. Мурино (Всеволожский р-н)", 60.0550, 30.4300),
                        ("г. Пикалёво (Бокситогорский р-н)", 59.5130, 34.1750),
                        ("г. Сясьстрой (Волховский р-н)", 60.1360, 32.5690),
                    ],
                    format_func=lambda x: x[0],
                )
            with col_b:
                payload["lat"] = st.number_input("Широта (Latitude):", value=preset[1], format="%.5f")
            with col_c:
                payload["lon"] = st.number_input("Долгота (Longitude):", value=preset[2], format="%.5f")
            payload["limit"] = st.slider("Количество ближайших случаев:", 10, 200, 100)

        elif q_choice == "q3_periods":
            payload["district"] = st.selectbox(
                "Выберите район:",
                [
                    "Василеостровский район (СПб)",
                    "Всеволожский район (Мурино / Кудрово / Бугры)",
                    "Бокситогорский район (Пикалёво / Бор / Ефимовский)",
                    "Волховский район (Сясьстрой / Новая Ладога / Паша)",
                ],
            )
            p1, p2, p3, p4 = st.columns(4)
            payload["p1_start"] = str(p1.date_input("Период 1 (С):", pd.to_datetime("2018-01-01")))
            payload["p1_end"] = str(p2.date_input("Период 1 (По):", pd.to_datetime("2024-08-02")))
            payload["p2_start"] = str(p3.date_input("Период 2 (С):", pd.to_datetime("2024-08-03")))
            payload["p2_end"] = str(p4.date_input("Период 2 (По):", pd.to_datetime("2024-12-31")))

        elif q_choice == "q5_group_age":
            payload["group_field"] = st.selectbox(
                "Признак группировки:",
                [
                    ("severity", "По степени тяжести состояния (Severity)"),
                    ("region", "По территории (Санкт-Петербург / Ленинградская обл.)"),
                    ("social_group", "По социальной группе (Social_group)"),
                    ("diagnosis", "По диагнозу (Therapy.diagnosis)"),
                    ("source", "По заболеванию (COVID-19 vs Туберкулёз)"),
                ],
                format_func=lambda x: x[1],
            )[0]

        if st.button("▶️ Выполнить запрос", type="primary", width="stretch"):
            res = api_post_json("/v1/tz-query", payload)
            st.success(res.get("description", "Выполнено"))

            if res.get("mode") == "spatial":
                st.metric("Найдено случаев в выборке", res.get("matched_count", 0))
                res_rows = res.get("results", [])
                if res_rows:
                    maps.render(res_rows)
                    st.dataframe(pd.DataFrame(res_rows), width="stretch", hide_index=True)
                    geojson_str = json.dumps(res.get("geojson", {}), ensure_ascii=False, indent=2)
                    st.download_button(
                        label=f"📥 Скачать слой этого запроса в GeoJSON для QGIS ({len(res_rows)} точек)",
                        data=geojson_str,
                        file_name=f"qgis_{q_choice}.geojson",
                        mime="application/geo+json",
                        width="stretch",
                    )
                else:
                    st.info("В указанном районе или диапазоне дат случаев не найдено.")
            else:
                res_rows = res.get("results", [])
                if res_rows:
                    df_agg = pd.DataFrame(res_rows)
                    st.dataframe(df_agg, width="stretch", hide_index=True)
                    if len(df_agg.columns) >= 2:
                        st.bar_chart(df_agg.set_index(df_agg.columns[0])[df_agg.columns[1]])

            with st.expander("🛠️ Показать сформированную JSON и XML разметку запроса (для тимлида и отчёта)"):
                q_json = json.dumps(res.get("mongo_query", {}), ensure_ascii=False, indent=2)
                st.markdown("**1. Сформированный JSON-запрос к СУБД:**")
                st.code(q_json, language="json")
                xml_repr = (
                    f'<?xml version="1.0" encoding="UTF-8"?>\n'
                    f'<gisQuery role="{selected_role}" type="{q_choice}">\n'
                    f'  <payload>{saxutils.escape(json.dumps(payload, ensure_ascii=False))}</payload>\n'
                    f'  <compiledMongoQuery>{saxutils.escape(q_json)}</compiledMongoQuery>\n'
                    f'</gisQuery>'
                )
                st.markdown("**2. Сформированная XML-разметка запроса:**")
                st.code(xml_repr, language="xml")

    with tab_upload:
        st.subheader("📥 Импорт геопакетов (.gpkg) в приёмник `cases` и 17 коллекций `Schema`")
        uploaded_files = st.file_uploader(
            "Перетащите сюда оба ваших файла .gpkg (COVID-19 и Туберкулёз):",
            type=["gpkg"],
            accept_multiple_files=True,
        )

        col_up1, col_up2 = st.columns([3, 1])
        with col_up1:
            if st.button("🚀 Загрузить файлы .gpkg и распределить по 17 коллекциям", type="primary", width="stretch"):
                if not uploaded_files:
                    st.warning("Сначала выберите файлы .gpkg!")
                else:
                    for uf in uploaded_files:
                        with st.spinner(f"Обработка {uf.name}: запись в cases и 17 коллекций схемы..."):
                            ans = api_upload_gpkg(uf.getvalue(), uf.name)
                            st.success(
                                f"✅ Файл **{uf.name}** ({ans.get('dataset_type')}) загружен! "
                                f"Добавлено записей: **{ans.get('imported')}** во все коллекции схемы."
                            )
                    st.rerun()

        with col_up2:
            if st.button("🗑️ Очистить базу", width="stretch"):
                api_post_json("/v1/clear-cases")
                st.rerun()

        st.markdown("---")
        st.subheader("🗄️ Состояние всех 17 предметных коллекций тимлида + буфера `cases`")
        rows_col = []
        for col_name, cnt in counts.items():
            rows_col.append({
                "Коллекция MongoDB": f"Schema.{col_name}",
                "Документов": 0 if cnt == -1 else cnt,
                "Права доступа текущей роли": "🔒 Доступ закрыт (RBAC)" if cnt == -1 else "✅ Чтение разрешено",
            })
        st.dataframe(pd.DataFrame(rows_col), width="stretch", hide_index=True)

        if sample_5:
            with st.expander("👀 Посмотреть 5 случайных документов из коллекции `cases` (по чек-листу ТЗ)"):
                st.json(sample_5)

    with tab_qgis:
        st.subheader("🛰️ Интеграция с QGIS и Прямой конструктор JSON/XML запросов")
        st.markdown("**Ссылка для подключения живого слоя очагов в QGIS:**")
        st.code(f"http://127.0.0.1:8000/v1/geojson?role={selected_role}", language="text")

        st.markdown("---")
        st.markdown("#### 🧬 Прямая отправка JSON или XML запроса к коллекциям `Schema`")
        custom_col = st.selectbox("Коллекция:", ["Patient", "Therapy", "Geodata", "Region", "Settlement", "Street", "Building"])
        fmt_mode = st.radio("Формат:", ["JSON", "XML"], horizontal=True)
        if fmt_mode == "JSON":
            default_q = json.dumps({"role": selected_role, "collection": f"Schema.{custom_col}", "filter": {}, "limit": 25}, indent=2)
        else:
            default_q = f'<gisQuery role="{selected_role}">\n  <collection>{custom_col}</collection>\n  <filters></filters>\n  <limit>25</limit>\n</gisQuery>'
        raw_q = st.text_area("Текст запроса:", value=default_q, height=160)
        if st.button("Отправить пакет в СУБД"):
            try:
                ctype = "application/json" if fmt_mode == "JSON" else "application/xml"
                r_out = api_post_json("/v1/query", raw_text=raw_q, content_type=ctype)
                st.success(f"Найдено документов в {r_out.get('collection')}: {r_out.get('matched_count')}")
                st.dataframe(pd.DataFrame(r_out.get("results", [])), width="stretch")
            except Exception as exc:
                st.error(f"Отказ доступа или ошибка запроса: {exc}")


if __name__ == "__main__":
    main()