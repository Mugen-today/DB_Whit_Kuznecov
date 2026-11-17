"""Spatial queries module: Polygon containment, Nearest 100 cases, and Two-Period comparison."""

import math
from . import export_data

DISTRICT_POLYGONS = {
    "Василеостровский район (СПб)": {
        "min_lat": 59.915, "max_lat": 59.965, "min_lon": 30.190, "max_lon": 30.310,
        "polygon": [[[30.190, 59.915], [30.310, 59.915], [30.310, 59.965], [30.190, 59.965], [30.190, 59.915]]],
    },
    "Центральный и Адмиралтейский р-ны (СПб)": {
        "min_lat": 59.900, "max_lat": 59.955, "min_lon": 30.280, "max_lon": 30.400,
        "polygon": [[[30.280, 59.900], [30.400, 59.900], [30.400, 59.955], [30.280, 59.955], [30.280, 59.900]]],
    },
    "Всеволожский район (Мурино / Кудрово / Бугры)": {
        "min_lat": 59.880, "max_lat": 60.250, "min_lon": 30.350, "max_lon": 30.850,
        "polygon": [[[30.350, 59.880], [30.850, 59.880], [30.850, 60.250], [30.350, 60.250], [30.350, 59.880]]],
    },
    "Бокситогорский район (Пикалёво / Бор / Ефимовский)": {
        "min_lat": 59.000, "max_lat": 60.050, "min_lon": 33.400, "max_lon": 35.300,
        "polygon": [[[33.400, 59.000], [35.300, 59.000], [35.300, 60.050], [33.400, 60.050], [33.400, 59.000]]],
    },
    "Волховский район (Сясьстрой / Новая Ладога / Паша)": {
        "min_lat": 59.700, "max_lat": 60.650, "min_lon": 32.000, "max_lon": 33.650,
        "polygon": [[[32.000, 59.700], [33.650, 59.700], [33.650, 60.650], [32.000, 60.650], [32.000, 59.700]]],
    },
    "Волосовский район (Бегуницы / Извара / Кикерино)": {
        "min_lat": 59.100, "max_lat": 59.750, "min_lon": 28.800, "max_lon": 30.050,
        "polygon": [[[28.800, 59.100], [30.050, 59.100], [30.050, 59.750], [28.800, 59.750], [28.800, 59.100]]],
    },
}


def _haversine_km(lat1, lon1, lat2, lon2):
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def execute(*args, **kwargs):
    if not args and "store" not in kwargs:
        raise NotImplementedError("spatial is outside the current Storage scope")

    store = args[0] if args else kwargs["store"]
    payload = kwargs.get("payload", {})
    role = payload.get("role", "reader")
    q_type = payload.get("query_type", "q1_polygon")

    all_data = export_data.execute(store, role=role)
    records = [r for r in all_data.get("records", []) if r.get("lat") is not None and r.get("lon") is not None]

    if q_type == "q1_polygon":
        district = payload.get("district", "Василеостровский район (СПб)")
        box = DISTRICT_POLYGONS.get(district, DISTRICT_POLYGONS["Василеостровский район (СПб)"])
        matched = [
            r for r in records
            if box["min_lat"] <= r["lat"] <= box["max_lat"] and box["min_lon"] <= r["lon"] <= box["max_lon"]
        ]
        mongo_query = {
            "target_collections": ["Schema.Foci", "Schema.Location", "Schema.Geodata"],
            "filter": {
                "Latitude": {"$gte": box["min_lat"], "$lte": box["max_lat"]},
                "Longitude": {"$gte": box["min_lon"], "$lte": box["max_lon"]},
                "$geoWithin": {"$geometry": {"type": "Polygon", "coordinates": box["polygon"]}},
            },
        }
        desc = f"Запрос 1 (ТЗ): Случаи внутри полигона «{district}»"

    elif q_type == "q2_nearest":
        lat = float(payload.get("lat", 59.9426))
        lon = float(payload.get("lon", 30.2783))
        limit_n = int(payload.get("limit", 100))
        with_dist = []
        for r in records:
            r_copy = dict(r)
            r_copy["distance_km"] = round(_haversine_km(lat, lon, r["lat"], r["lon"]), 2)
            with_dist.append(r_copy)
        with_dist.sort(key=lambda x: x["distance_km"])
        matched = with_dist[:limit_n]
        mongo_query = {
            "target_collections": ["Schema.Geodata", "Schema.Location", "Schema.Foci"],
            "near_point": {"Latitude": lat, "Longitude": lon},
            "limit": limit_n,
        }
        desc = f"Запрос 2 (ТЗ): {limit_n} ближайших случаев к координатам [{lat}, {lon}]"

    else:  # q3_periods
        district = payload.get("district", "Василеостровский район (СПб)")
        box = DISTRICT_POLYGONS.get(district, DISTRICT_POLYGONS["Василеостровский район (СПб)"])
        p1_s = payload.get("p1_start", "2020-01-01")
        p1_e = payload.get("p1_end", "2023-12-31")
        p2_s = payload.get("p2_start", "2024-01-01")
        p2_e = payload.get("p2_end", "2024-12-31")
        matched = []
        for r in records:
            if not (box["min_lat"] <= r["lat"] <= box["max_lat"] and box["min_lon"] <= r["lon"] <= box["max_lon"]):
                continue
            dt = r.get("date", "")
            if p1_s <= dt <= p1_e:
                rc = dict(r)
                rc["period_group"] = f"Период 1 ({p1_s} .. {p1_e})"
                matched.append(rc)
            elif p2_s <= dt <= p2_e:
                rc = dict(r)
                rc["period_group"] = f"Период 2 ({p2_s} .. {p2_e})"
                matched.append(rc)

        mongo_query = {
            "target_collections": ["Schema.Instances", "Schema.Foci", "Schema.Geodata"],
            "filter": {
                "Latitude": {"$gte": box["min_lat"], "$lte": box["max_lat"]},
                "Longitude": {"$gte": box["min_lon"], "$lte": box["max_lon"]},
                "$or": [
                    {"Instances.date": {"$gte": p1_s, "$lte": p1_e}},
                    {"Instances.date": {"$gte": p2_s, "$lte": p2_e}},
                ],
            },
        }
        desc = f"Запрос 3 (ТЗ): Сравнение 2 периодов в районе «{district}»"

    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(r["lon"]), float(r["lat"])]},
            "properties": r,
        }
        for r in matched
    ]

    return {
        "status": "ok",
        "mode": "spatial",
        "description": desc,
        "matched_count": len(matched),
        "mongo_query": mongo_query,
        "results": matched,
        "geojson": {"type": "FeatureCollection", "name": f"QGIS_{q_type}", "features": features},
    }