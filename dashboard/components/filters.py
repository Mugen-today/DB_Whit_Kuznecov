"""Фильтры медицинских данных для сотрудников медучреждений."""

from datetime import date
import pandas as pd
import streamlit as st


def _unique_sorted(df, col):
    if col not in df.columns:
        return []
    vals = [str(v).strip() for v in df[col].dropna().unique() if str(v).strip() and str(v).strip() != "None"]
    return sorted(set(vals))


def render(records, *args, **kwargs):
    st.sidebar.markdown("### Фильтрация записей")
    if not records:
        st.sidebar.info("Нет доступных записей.")
        return []

    if st.sidebar.button("Сбросить все фильтры", width="stretch"):
        for key in list(st.session_state.keys()):
            if key.startswith("flt_"):
                del st.session_state[key]
        st.rerun()

    df = pd.DataFrame(records)

    # 1. Быстрый текстовый поиск
    search_query = st.sidebar.text_input(
        "Поиск по адресу, улице или симптомам",
        placeholder="Введите улицу, город, препарат...",
        key="flt_search",
    ).strip().lower()

    # 2. Период дат обращения
    valid_dates = pd.to_datetime(df.get("date", pd.Series(dtype=str)), errors="coerce").dropna()
    if not valid_dates.empty:
        min_dt = valid_dates.min().date()
        max_dt = valid_dates.max().date()
    else:
        min_dt = date(2018, 1, 1)
        max_dt = date.today()

    date_bounds = st.sidebar.date_input(
        "Период регистрации",
        value=(min_dt, max_dt),
        min_value=min_dt,
        max_value=max_dt,
        key="flt_dates",
    )

    # 3. Профиль заболевания
    sources = _unique_sorted(df, "source")
    selected_sources = st.sidebar.multiselect(
        "Профиль заболевания",
        options=sources,
        default=[],
        placeholder="Все профили",
        key="flt_source",
    )

    # 4. Диагноз
    diagnoses = _unique_sorted(df, "diagnosis")
    selected_diag = st.sidebar.multiselect(
        "Диагноз",
        options=diagnoses,
        default=[],
        placeholder="Все диагнозы",
        key="flt_diag",
    )

    # 5. Тяжесть течения
    severities = _unique_sorted(df, "severity")
    selected_sev = st.sidebar.multiselect(
        "Степень тяжести",
        options=severities,
        default=[],
        placeholder="Любая тяжесть",
        key="flt_sev",
    )

    # 6. Территория и населенный пункт
    regions = _unique_sorted(df, "region")
    selected_regions = st.sidebar.multiselect(
        "Субъект",
        options=regions,
        default=[],
        placeholder="Все субъекты",
        key="flt_reg",
    )

    municipalities = _unique_sorted(df, "municipality")
    selected_mun = st.sidebar.multiselect(
        "Район",
        options=municipalities,
        default=[],
        placeholder="Все районы",
        key="flt_mun",
    )

    settlements = _unique_sorted(df, "settlement")
    selected_settl = st.sidebar.multiselect(
        "Населенный пункт",
        options=settlements,
        default=[],
        placeholder="Все населенные пункты",
        key="flt_settl",
    )

    # 7. Медицинское учреждение и социальная категория
    hospitals = _unique_sorted(df, "hospital")
    selected_hosp = st.sidebar.multiselect(
        "Медицинское учреждение или режим",
        options=hospitals,
        default=[],
        placeholder="Все учреждения",
        key="flt_hosp",
    )

    social_groups = _unique_sorted(df, "social_group")
    selected_soc = st.sidebar.multiselect(
        "Социальная категория",
        options=social_groups,
        default=[],
        placeholder="Все категории",
        key="flt_soc",
    )

    # 8. Исход лечения
    outcomes = _unique_sorted(df, "outcome")
    selected_outcomes = st.sidebar.multiselect(
        "Исход наблюдения",
        options=outcomes,
        default=[],
        placeholder="Любой исход",
        key="flt_out",
    )

    # 9. Возраст пациента
    ages = [int(r["age"]) for r in records if isinstance(r.get("age"), (int, float)) and r.get("age") is not None]
    min_age = min(ages) if ages else 0
    max_age = max(ages) if ages else 100
    if min_age >= max_age:
        min_age, max_age = 0, 100

    age_range = st.sidebar.slider(
        "Возраст пациента, лет",
        min_value=0,
        max_value=130,
        value=(max(0,min(130,min_age)), max(0,min(130,max_age))),
        key="flt_age",
    )

    # 10. Признаки госпитализации и рецидива
    col_f1, col_f2 = st.sidebar.columns(2)
    only_hosp = col_f1.checkbox("Госпитализация", value=False, key="flt_only_hosp")
    only_relapse = col_f2.checkbox("Рецидив", value=False, key="flt_only_rel")

    date_start_str = str(date_bounds[0]) if isinstance(date_bounds, (list, tuple)) and len(date_bounds) >= 1 else None
    date_end_str = str(date_bounds[1]) if isinstance(date_bounds, (list, tuple)) and len(date_bounds) >= 2 else date_start_str

    filtered = []
    for r in records:
        if selected_sources and str(r.get("source", "")).strip() not in selected_sources:
            continue
        if selected_diag and str(r.get("diagnosis", "")).strip() not in selected_diag:
            continue
        if selected_sev and str(r.get("severity", "")).strip() not in selected_sev:
            continue
        if selected_regions and str(r.get("region", "")).strip() not in selected_regions:
            continue
        if selected_mun and str(r.get("municipality", "")).strip() not in selected_mun:
            continue
        if selected_settl and str(r.get("settlement", "")).strip() not in selected_settl:
            continue
        if selected_hosp and str(r.get("hospital", "")).strip() not in selected_hosp:
            continue
        if selected_soc and str(r.get("social_group", "")).strip() not in selected_soc:
            continue
        if selected_outcomes and str(r.get("outcome", "")).strip() not in selected_outcomes:
            continue

        rec_date = str(r.get("date", ""))[:10]
        if date_start_str and date_end_str and len(rec_date) == 10:
            if not (date_start_str <= rec_date <= date_end_str):
                continue

        age_val = r.get("age")
        if isinstance(age_val, (int, float)):
            if not (age_range[0] <= age_val <= age_range[1]):
                continue

        if only_hosp and not r.get("hospitalized"):
            continue
        if only_relapse and not r.get("relapse"):
            continue

        if search_query:
            searchable_text = " ".join([
                str(r.get("address", "")),
                str(r.get("diagnosis", "")),
                str(r.get("hospital", "")),
                str(r.get("symptoms", "")),
                str(r.get("settlement", "")),
                str(r.get("municipality", "")),
                str(r.get("social_group", "")),
            ]).lower()
            if search_query not in searchable_text:
                continue

        filtered.append(r)

    st.sidebar.markdown(f"**Найдено записей: {len(filtered)} из {len(records)}**")
    return filtered