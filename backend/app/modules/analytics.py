"""Analytics module: Time-series grouping, Attribute grouping with average age, and $unwind Top-5."""

from collections import Counter, defaultdict
from . import export_data


def execute(*args, **kwargs):
    if not args and "store" not in kwargs:
        raise NotImplementedError("analytics is outside the current Storage scope")

    store = args[0] if args else kwargs["store"]
    payload = kwargs.get("payload", {})
    role = payload.get("role", "reader")
    q_type = payload.get("query_type", "q4_timeseries")

    all_data = export_data.execute(store, role=role)
    records = all_data.get("records", [])

    if q_type == "q4_timeseries":
        counts_by_date = Counter(r.get("date", "Не указана") for r in records if r.get("date"))
        sorted_rows = [
            {"Дата обращения": dt, "Количество случаев": cnt}
            for dt, cnt in sorted(counts_by_date.items())
        ]
        pipeline = [
            {"$group": {"_id": "$date", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]
        return {
            "status": "ok",
            "mode": "aggregation",
            "description": "Запрос 4 (ТЗ): Динамика случаев по датам (временной ряд из Schema.Instances)",
            "mongo_query": {"collection": "Schema.Instances", "pipeline": pipeline},
            "results": sorted_rows,
        }

    elif q_type == "q5_group_age":
        group_field = payload.get("group_field", "severity")
        groups_cnt = Counter()
        groups_ages = defaultdict(list)

        for r in records:
            key = str(r.get(group_field) or "Не указано")
            groups_cnt[key] += 1
            if isinstance(r.get("age"), (int, float)):
                groups_ages[key].append(r["age"])

        rows = []
        for key, cnt in groups_cnt.most_common():
            ages = groups_ages[key]
            avg_age = round(sum(ages) / len(ages), 1) if ages else 0.0
            rows.append({
                "Категория": key,
                "Количество случаев": cnt,
                "Средний возраст (лет)": avg_age,
            })

        pipeline = [
            {"$lookup": {"from": "Patient", "localField": "patient", "foreignField": "_id", "as": "pat"}},
            {"$unwind": "$pat"},
            {"$group": {"_id": f"${group_field}", "count": {"$sum": 1}, "avg_age": {"$avg": "$pat.age"}}},
            {"$sort": {"count": -1}},
        ]
        return {
            "status": "ok",
            "mode": "aggregation",
            "description": f"Запрос 5 (ТЗ): Группировка по «{group_field}» с расчётом среднего возраста (Schema.Patient + Therapy)",
            "mongo_query": {"collection": "Schema.Instances", "pipeline": pipeline},
            "results": rows,
        }

    else:  # q6_unwind
        item_counter = Counter()
        for r in records:
            for item in r.get("items_array", []):
                if item and item not in ("Выздоровел", "На наблюдении"):
                    item_counter[item] += 1

        rows = [
            {"Симптом (COVID-19) / Препарат устойчивости (ТБ)": k, "Частота выявления": v}
            for k, v in item_counter.most_common(5)
        ]
        pipeline = [
            {"$unwind": "$effect_treatment"},
            {"$group": {"_id": "$effect_treatment", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5},
        ]
        return {
            "status": "ok",
            "mode": "aggregation",
            "description": "Запрос 6 (ТЗ): Развёртывание массивов ($unwind) — Топ-5 частых симптомов и устойчивости к препаратам",
            "mongo_query": {"collection": "Schema.Therapy", "pipeline": pipeline},
            "results": rows,
        }