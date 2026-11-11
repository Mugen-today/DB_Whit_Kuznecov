"""Аналитическая панель эпидемиологического мониторинга с разграничением прав (RBAC)."""

import json
import os
import urllib.request

import pandas as pd
import streamlit as st

from components import charts, filters, maps

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000").rstrip("/")

ROLE_ACCOUNTS = {
    "reader": {
        "title": "Главный врач и аналитик",
        "password": os.getenv("ROLE_READER_PASS", ""),
        "role": "reader",
    },
    "user": {
        "title": "Дежурный врач отделения",
        "password": os.getenv("ROLE_USER_PASS", ""),
        "role": "user",
    },
    "guest": {
        "title": "Внешний исследователь",
        "password": os.getenv("ROLE_GUEST_PASS", ""),
        "role": "guest",
    },
}

COLLECTION_FIELDS_HINT = {
    "Patient": ["age", "passport", "gender", "social_group", "reg_date"],
    "Therapy": ["diagnosis", "hospitalization", "relapse", "effect_treatment", "other"],
    "Geodata": ["Latitude", "Longitude", "Elevation"],
    "Instances": ["date", "Other", "patient", "therapy", "reception"],
    "Foci": ["location", "id_instance"],
    "Region": ["name", "municipality"],
    "Municipality": ["name", "settlement"],
    "Settlement": ["name", "type", "street"],
    "Street": ["name", "building"],
    "Building": ["house", "corpus", "edificate", "placement"],
    "Placement": ["number"],
    "Severity": ["degree"],
    "Social_group": ["type"],
    "Influence": ["name"],
    "Reception": ["type"],
    "Gender": ["type"],
    
}


def api_headers():
    role=st.session_state.get("auth_role")
    key={"reader":"DASHBOARD_TOKEN","user":"QGIS_USER_TOKEN","guest":"QGIS_GUEST_TOKEN"}.get(role)
    return {"Authorization":"Bearer "+os.environ.get(key or "", "")}

def api_get(path):
    req = urllib.request.Request(f"{BACKEND_URL}{path}", method="GET", headers=api_headers())
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


@st.cache_data(ttl=60, show_spinner=False)
def cached_overview(role):
    import urllib.parse
    records=[];cursor=None;overview={}
    while True:
        path=f"/v1/overview?role={role}&limit=500"+("&after="+urllib.parse.quote(cursor,safe="") if cursor else "")
        page=api_get(path)
        records.extend(page.get("records",[]))
        if not overview:overview=page
        cursor=page.get("next")
        if not cursor:break
        # Other profiles retain the bounded interface; the analyst processes the full dataset.
        if role!="reader" and len(records)>=2500:break
    return {**overview,"records":records,"loaded_records":len(records)}


def api_post_raw(path, raw_text, content_type="application/json"):
    req = urllib.request.Request(
        f"{BACKEND_URL}{path}",
        data=raw_text.encode("utf-8"),
        headers={**api_headers(), "Content-Type": content_type},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def render_auth_sidebar():
    st.sidebar.markdown("### Вход в систему")

    if "auth_role" not in st.session_state:
        st.session_state["auth_role"] = None

    if st.session_state["auth_role"]:
        active = ROLE_ACCOUNTS[st.session_state["auth_role"]]
        st.sidebar.success(f"Профиль: **{active['title']}**")
        if st.sidebar.button("Выйти из системы", width="stretch"):
            st.session_state["auth_role"] = None
            st.cache_data.clear()
            st.rerun()
        return st.session_state["auth_role"]

    selected_account = st.sidebar.selectbox(
        "Должность",
        options=list(ROLE_ACCOUNTS.keys()),
        format_func=lambda k: ROLE_ACCOUNTS[k]["title"],
    )
    entered_password = st.sidebar.text_input("Пароль", type="password")

    if st.sidebar.button("Войти", type="primary", width="stretch"):
        expected_password = ROLE_ACCOUNTS[selected_account]["password"]
        import hmac
        if expected_password and hmac.compare_digest(entered_password.encode("utf-8"), expected_password.encode("utf-8")):
            st.session_state["auth_role"] = selected_account
            st.cache_data.clear()
            st.rerun()
        else:
            st.sidebar.error("Неверный пароль.")

    st.sidebar.caption("Пароли профилей задаются в .env: ROLE_READER_PASS, ROLE_USER_PASS, ROLE_GUEST_PASS.")
    return None


def main():
    st.set_page_config(page_title="Эпидемиологический мониторинг", page_icon="🏥", layout="wide")
    st.title("Система эпидемиологического мониторинга Санкт-Петербурга и Ленинградской области")

    auth_role = render_auth_sidebar()
    if not auth_role:
        st.info("Авторизуйтесь в боковой панели слева для просмотра аналитических данных.")
        return

    if st.sidebar.button("Обновить данные из базы", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    try:
        overview = cached_overview(auth_role)
    except Exception as exc:
        st.error(f"Нет связи с сервером базы данных по адресу {BACKEND_URL}. Детали: {exc}")
        return

    records = overview.get("records", [])
    counts = overview.get("counts", {})
    total_instances = overview.get("total_instances", 0)

    # Принудительное обезличивание данных для внешнего исследователя
    if auth_role == "guest":
        for r in records:
            r["address"] = f"{r.get('region', '')}, {r.get('municipality', '')} [Адрес скрыт]"
            r["social_group"] = "[Обезличено]"
            r["symptoms"] = "[Обезличено]"

    st.sidebar.markdown("---")
    filtered_records = filters.render(records)

    tab_map, tab_charts, tab_journal, tab_export = st.tabs([
        "Сводка и карта очагов",
        "Статистические графики",
        "Журнал обращений",
        "Выгрузка геоданных и коллекции",
    ])

    # ВКЛАДКА 1: ОБЩАЯ СТАТИСТИКА И КАРТА
    with tab_map:
        total_filtered = len(filtered_records)
        covid_cnt = sum(1 for r in filtered_records if "COVID" in str(r.get("source", "")))
        tb_cnt = sum(1 for r in filtered_records if "Туберкулёз" in str(r.get("source", "")))
        hosp_cnt = sum(1 for r in filtered_records if r.get("hospitalized"))
        relapse_cnt = sum(1 for r in filtered_records if r.get("relapse"))

        k1, k2, k3, k4, k5, k6 = st.columns(6)
        st.info("Исторические записи могут не иметь диагноза или связанной терапии. Карта показывает только записи с установленной связью с геоданными; отдельные точки доступны через коллекцию Geodata в QGIS.")
        st.caption("Анализируются все загруженные обращения: "+str(len(records)) if auth_role=="reader" else "Для этого профиля интерфейс ограничен 2500 обращениями.")
        k1.metric("Всего в базе", max(0, total_instances))
        k2.metric("Отобрано фильтром", total_filtered)
        k3.metric("Респираторные вирусные инфекции", covid_cnt)
        k4.metric("Туберкулёз", tb_cnt)
        k5.metric("Госпитализировано", hosp_cnt)
        k6.metric("Рецидивы", relapse_cnt)

        st.markdown("---")
        if auth_role == "guest":
            st.warning(
                "Режим внешнего исследователя: персональные адресные данные, социальные категории "
                "и симптоматика скрыты в этом профиле."
            )

        st.subheader("Пространственное распределение связанных записей")
        if not filtered_records:
            st.info("По выбранным параметрам фильтра записи отсутствуют.")
        else:
            maps.render(filtered_records)

    # ВКЛАДКА 2: ГРАФИКИ
    with tab_charts:
        charts.render(filtered_records)

    # ВКЛАДКА 3: СВОДНЫЙ ЖУРНАЛ И СРЕДА ЗАПРОСОВ (ТОЛЬКО ДЛЯ АНАЛИТИКА)
    with tab_journal:
        # Для аналитика даем переключатель с консолью, для остальных — только журнал
        if auth_role == "reader":
            mode = st.radio(
                "Режим работы",
                [
                    "Сводный журнал пациентов",
                    "Консоль запросов через backend для аналитика",
                ],
                horizontal=True,
            )
        else:
            mode = "Сводный журнал пациентов"

        if mode == "Сводный журнал пациентов":
            st.subheader("Реестр зарегистрированных случаев")
            if not filtered_records:
                st.info("Нет записей для отображения в журнале.")
            else:
                page_size = 100
                total_rec = len(filtered_records)
                total_pages = max(1, (total_rec + page_size - 1) // page_size)

                p_col1, p_col2, p_col3 = st.columns([1, 2, 2])
                with p_col1:
                    page_num = st.number_input("Номер страницы", min_value=1, max_value=total_pages, value=1)
                with p_col2:
                    st.caption(
                        f"Записи с {(page_num - 1) * page_size + 1} по {min(page_num * page_size, total_rec)} из {total_rec}"
                    )
                with p_col3:
                    csv_bytes = pd.DataFrame(filtered_records).to_csv(index=False).encode("utf-8-sig")
                    st.download_button(
                        "Выгрузить таблицу в CSV",
                        data=csv_bytes,
                        file_name="medical_journal.csv",
                        mime="text/csv",
                        width="stretch",
                    )

                page_slice = filtered_records[(page_num - 1) * page_size : page_num * page_size]
                df_display = pd.DataFrame(page_slice).rename(columns={
                    "date": "Дата",
                    "source": "Профиль",
                    "diagnosis": "Диагноз",
                    "severity": "Тяжесть",
                    "age": "Возраст",
                    "region": "Субъект",
                    "municipality": "Район",
                    "settlement": "Населенный пункт",
                    "address": "Адрес очага",
                    "social_group": "Социальная категория",
                    "hospital": "Учреждение или режим",
                    "symptoms": "Симптомы и устойчивость",
                    "outcome": "Исход",
                })
                cols_to_show = [
                    "Дата", "Профиль", "Диагноз", "Тяжесть", "Возраст",
                    "Субъект", "Район", "Населенный пункт", "Адрес очага",
                    "Социальная категория", "Учреждение или режим", "Симптомы и устойчивость", "Исход",
                ]
                st.dataframe(
                    df_display[[c for c in cols_to_show if c in df_display.columns]],
                    width="stretch",
                    hide_index=True,
                )

        else:
            # КОНСОЛЬ ДОСТУПНА ТОЛЬКО РОЛИ READER
            st.subheader("Консоль аналитика: выполнение прямых запросов к коллекциям СУБД")
            col_q1, col_q2, col_q3 = st.columns([1.5, 1, 1.5])
            with col_q1:
                target_col = st.selectbox(
                    "Коллекция базы данных",
                    list(COLLECTION_FIELDS_HINT.keys()),
                )
            with col_q2:
                query_fmt = st.radio(
                    "Формат разметки",
                    ["JSON", "XML"],
                    horizontal=True,
                )
            with col_q3:
                limit_docs = st.number_input("Максимальное число строк", min_value=1, max_value=200, value=100, step=10)

            fields_hint = ", ".join(f"`{f}`" for f in COLLECTION_FIELDS_HINT.get(target_col, []))
            st.caption(f"Поля выбранной коллекции: {fields_hint}")

            preset_template = st.selectbox(
                "Шаблон условия",
                [
                    "Все записи коллекции",
                    "Фильтр по числовому диапазону",
                    "Поиск по текстовому шаблону",
                    "Точное совпадение значения",
                ],
            )

            if query_fmt == "JSON":
                if preset_template == "Все записи коллекции":
                    sample_filter = {}
                elif preset_template == "Фильтр по числовому диапазону":
                    num_field = "age" if target_col == "Patient" else ("Latitude" if target_col == "Geodata" else "house")
                    sample_filter = {num_field: {"$gte": 30, "$lte": 70}} if num_field != "Latitude" else {"Latitude": {"$gte": 59.9, "$lte": 60.1}}
                elif preset_template == "Поиск по текстовому шаблону":
                    str_field = "name" if target_col in ("Region", "Municipality", "Settlement", "Street") else "other"
                    sample_filter = {str_field: {"$regex": "Санкт-Петербург|Мурино|Всеволожск", "$options": "i"}}
                else:
                    bool_field = "hospitalization" if target_col == "Therapy" else "degree"
                    sample_filter = {bool_field: True} if bool_field == "hospitalization" else {"degree": "Тяжелая"}

                default_payload = json.dumps(
                    {
                        "role": auth_role,
                        "collection": f"Schema.{target_col}",
                        "filter": sample_filter,
                        "limit": int(limit_docs),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            else:
                default_field = COLLECTION_FIELDS_HINT.get(target_col, ["_id"])[0]
                default_payload = (
                    f'<?xml version="1.0" encoding="UTF-8"?>\n'
                    f'<gisQuery role="{auth_role}">\n'
                    f'  <collection>{target_col}</collection>\n'
                    f'  <filters>\n'
                    f'    <condition field="{default_field}" operator="regex" type="string">.*</condition>\n'
                    f'  </filters>\n'
                    f'  <limit>{int(limit_docs)}</limit>\n'
                    f'</gisQuery>'
                )

            query_editor = st.text_area(
                "Текст запроса к базе данных",
                value=default_payload,
                height=200,
            )

            if st.button("Выполнить запрос и вывести в таблицу", type="primary", width="stretch"):
                ctype = "application/json" if query_fmt == "JSON" else "application/xml"
                try:
                    with st.spinner("Выполнение запроса..."):
                        res_q = api_post_raw("/v1/query", raw_text=query_editor, content_type=ctype)

                    st.success(f"Найдено записей: {res_q.get('matched_count', 0)}")
                    result_docs = res_q.get("results", [])
                    if result_docs:
                        df_res = pd.DataFrame(result_docs)
                        for c in df_res.columns:
                            df_res[c] = df_res[c].apply(
                                lambda v: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                            )
                        st.dataframe(df_res, width="stretch", hide_index=True)
                    else:
                        st.info("По заданному запросу документы не найдены.")
                except Exception as exc:
                    st.error(f"Отказ доступа или ошибка синтаксиса запроса: {exc}")

    # ВКЛАДКА 4: ВЫГРУЗКА ГЕОДАННЫХ И КОЛЛЕКЦИИ
    with tab_export:
        st.subheader("Экспорт пространственных данных")
        if st.button("Подготовить файл GeoJSON для скачивания", type="primary"):
            with st.spinner("Формирование геоданных..."):
                gj_data={"type":"FeatureCollection","features":[
                    {"type":"Feature","geometry":{"type":"Point","coordinates":[r["lon"],r["lat"]]},"properties":r}
                    for r in records if r.get("lon") is not None and r.get("lat") is not None]}
            st.download_button(
                label=f"Скачать файл GeoJSON, объектов: {len(gj_data.get('features', []))}",
                data=json.dumps(gj_data, ensure_ascii=False, indent=2),
                file_name=f"epid_foci_{auth_role}.geojson",
                mime="application/geo+json",
                width="stretch",
            )

        st.markdown("---")
        st.subheader("Наполнение коллекций базы данных")
        rows_col = [
            {
                "Коллекция": col_name,
                "Количество записей": 0 if cnt == -1 else cnt,
                "Статус доступа": "Доступ ограничен правами профиля" if cnt == -1 else "Чтение разрешено",
            }
            for col_name, cnt in counts.items()
        ]
        st.dataframe(pd.DataFrame(rows_col), width="stretch", hide_index=True)


if __name__ == "__main__":
    main()