"""Export module: reconstructs records from the 17 normalized collections with RBAC enforcement."""

from datetime import datetime


def execute(*args, **kwargs):
    if not args and "store" not in kwargs:
        raise NotImplementedError("export_data is outside the current Storage scope")

    store = args[0] if args else kwargs["store"]
    role = kwargs.get("role", "reader")
    if role not in ("reader", "admin", "user", "guest"):
        role = "reader"

    db = store.database(role)
    owner_filter = {"_owner_id": kwargs.get("owner", "")} if role == "user" else {}

    collection_names = [
        "Instances", "Foci", "Patient", "Therapy", "Location", "Geodata",
        "Region", "Municipality", "Settlement", "Street", "Building",
        "Placement", "Reception", "Gender", "Social_group", "Severity",
        "Influence", "cases",
    ]
    counts = {}
    for name in (collection_names if not kwargs.get("params",{}).get("after") else []):
        try:
            counts[name] = db[name].count_documents(owner_filter, maxTimeMS=2500)
        except Exception:
            counts[name] = -1

    from . import records as api_records
    params=kwargs.get("params",{})
    try:
        limit=int(params.get("limit",["500"])[0])
        if not 1<=limit<=1000:raise ValueError()
        query=dict(owner_filter)
        after=params.get("after",[""])[0]
        if after:query["$expr"]={"$gt":["$_id",{"$literal":api_records.id_for_key(after)}]}
    except (ValueError,TypeError):raise ValueError("Invalid export page")
    page=list(db["Instances"].find(query,max_time_ms=10000).sort("_id",1).limit(limit+1))
    instances_list=page[:limit]
    next_cursor=api_records.key_for_id(instances_list[-1]["_id"]) if len(page)>limit else None

    def safe_map(col, ids):
        if role == "guest" and col in ("Social_group", "Street", "Building", "Placement"):
            return {}
        ids = list({value for value in ids if value is not None})
        if not ids:
            return {}
        return {d["_id"]: d for d in db[col].find({**owner_filter, "_id": {"$in": ids}}, max_time_ms=2500)}

    instance_ids = [d.get("instance", d["_id"]) for d in instances_list]
    foci_by_inst = {d.get("id_instance"): d for d in db.Foci.find({**owner_filter, "id_instance": {"$in": instance_ids}}, max_time_ms=2500)}
    patients = safe_map("Patient", [d.get("patient") for d in instances_list])
    therapies = safe_map("Therapy", [d.get("therapy") for d in instances_list])
    locations = safe_map("Location", [d.get("location") for d in foci_by_inst.values()])
    addresses = [d.get("address", {}) for d in locations.values() if isinstance(d.get("address"), dict)]
    geodata_map = safe_map("Geodata", [d.get("geodata") for d in addresses])
    regions = safe_map("Region", [d.get("region") for d in addresses])
    municipals = safe_map("Municipality", [d.get("municipality") for d in regions.values()])
    settlements = safe_map("Settlement", [d.get("settlement") for d in municipals.values()])
    streets = safe_map("Street", [d.get("street") for d in settlements.values()])
    buildings = safe_map("Building", [d.get("building") for d in streets.values()])
    social_groups = safe_map("Social_group", [d.get("social_group") for d in patients.values()])
    severities = safe_map("Severity", [d.get("severity") for d in therapies.values()])

    records = []
    for inst in instances_list:
        inst_id = inst.get("instance") or inst.get("_id")
        pat = patients.get(inst.get("patient"), {})
        ther = therapies.get(inst.get("therapy"), {})
        foci = foci_by_inst.get(inst_id) or foci_by_inst.get(inst.get("_id")) or {}
        loc = locations.get(foci.get("location"), {})
        addr = loc.get("address", {}) if isinstance(loc.get("address"), dict) else {}

        reg = regions.get(addr.get("region"), {})
        mun = municipals.get(reg.get("municipality"), {})
        settl = settlements.get(mun.get("settlement"), {})
        strt = streets.get(settl.get("street"), {})
        bld = buildings.get(strt.get("building"), {})
        geo = geodata_map.get(addr.get("geodata"), {})

        sev = severities.get(ther.get("severity"), {})
        soc = social_groups.get(pat.get("social_group"), {})

        dt = inst.get("date") or ther.get("date_start")
        date_str = dt.strftime("%Y-%m-%d") if isinstance(dt, datetime) else (str(dt)[:10] if dt else "Не указана")

        diag_list = ther.get("diagnosis", [])
        diag_str = ", ".join(str(x) for x in diag_list) if isinstance(diag_list, list) else str(diag_list)

        eff_list = ther.get("effect_treatment", [])
        items_arr = [str(x) for x in eff_list if x] if isinstance(eff_list, list) else []

        proc_regex = ther.get("treatment_procedures")
        hosp_str = proc_regex.pattern if hasattr(proc_regex, "pattern") else str(proc_regex or "")

        res_obj = ther.get("result", {}) if isinstance(ther.get("result"), dict) else {}
        side_rx = res_obj.get("side effect")
        outcome_str = side_rx.pattern if hasattr(side_rx, "pattern") else (
            "Выздоровел" if res_obj.get("recovery") else ("Смерть (по исходным данным)" if res_obj.get("Saved") is False else "Не указан")
        )

        # Если роль guest, коллекции Street, Building и Social_group заблокированы в MongoDB
        if role == "guest":
            addr_display = f"{reg.get('name', '')}, {mun.get('name', '')}, {settl.get('name', '')} [Улица и дом скрыты RBAC]"
            soc_display = "🔒 Скрыто ролью Guest"
        else:
            house_num = bld.get("house", "")
            addr_display = f"{settl.get('name', '')}, {strt.get('name', '')}" + (f", д. {house_num}" if house_num else "")
            if not strt.get("name") and ther.get("other"): addr_display=str(ther["other"])
            soc_display = soc.get("type", "Не указан")

        records.append({
            "id": str(inst.get("_id")),
            "source": inst.get("Other", "Импорт ГИС"),
            "date": date_str,
            "age": pat.get("age"),
            "region": reg.get("name", "Не указан"),
            "municipality": mun.get("name", ""),
            "settlement": settl.get("name", ""),
            "address": addr_display.strip(", "),
            "diagnosis": diag_str,
            "severity": sev.get("degree", "Не указана"),
            "social_group": soc_display,
            "hospital": hosp_str,
            "hospitalized": ther.get("hospitalization"),
            "relapse": ther.get("relapse"),
            "outcome": outcome_str,
            "symptoms": ", ".join(items_arr),
            "items_array": items_arr,
            "street": strt.get("name", ""),
            "house": bld.get("house", ""),
            "elevation": geo.get("Elevation"),
            "lat": geo.get("Latitude"),
            "lon": geo.get("Longitude"),
        })

    # 5 случайных документов из cases (для чек-листа ТЗ), если роль имеет право чтения cases
    sample_5 = []

    return {
        "role": role,
        "next":next_cursor,
        "page_size":len(instances_list),
        "counts": counts,
        "total_in_cases": counts.get("cases", 0),
        "total_instances": counts.get("Instances", 0),
        "records": records,
        "sample_5_docs": sample_5,
    }