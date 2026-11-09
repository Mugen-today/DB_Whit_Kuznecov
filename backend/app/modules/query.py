"""Structured JSON/XML query processor for the 17 collections of Schema."""

import json
import xml.etree.ElementTree as ET


def execute(*args, **kwargs):
    if not args and "store" not in kwargs:
        raise NotImplementedError("query is outside the current Storage scope")

    store = args[0] if args else kwargs["store"]
    raw_text = kwargs.get("raw_text", "")
    content_type = kwargs.get("content_type", "application/json")

    if "xml" in content_type.lower() or raw_text.strip().startswith("<"):
        root = ET.fromstring(raw_text.strip())
        role = root.attrib.get("role", "reader")
        collection = (root.findtext("collection") or "Patient").replace("Schema.", "")
        limit = int(root.findtext("limit") or "50")
        mongo_filter = {}
        filters_node = root.find("filters")
        if filters_node is not None:
            for cond in filters_node.findall("condition"):
                field = cond.attrib.get("field")
                op = cond.attrib.get("operator", "eq")
                val_type = cond.attrib.get("type", "string")
                raw_val = cond.text or ""
                if val_type == "int":
                    val = int(raw_val)
                elif val_type == "float":
                    val = float(raw_val)
                elif val_type == "bool":
                    val = raw_val.lower() in ("true", "1", "yes")
                else:
                    val = raw_val

                if op == "eq":
                    mongo_filter[field] = val
                elif op in ("gt", "gte", "lt", "lte", "ne"):
                    mongo_filter.setdefault(field, {})[f"${op}"] = val
                elif op == "regex":
                    mongo_filter[field] = {"$regex": str(val), "$options": "i"}
        parsed_format = "XML"
    else:
        payload = json.loads(raw_text) if raw_text else {}
        role = payload.get("role", "reader")
        collection = payload.get("collection", "Patient").replace("Schema.", "")
        limit = int(payload.get("limit", 50))
        mongo_filter = payload.get("filter", {})
        parsed_format = "JSON"

    if role not in ("reader", "user", "guest"):
        role = "reader"

    db = store.database(role)
    docs = list(db[collection].find(mongo_filter).limit(min(limit, 200)))
    return {
        "status": "ok",
        "format_received": parsed_format,
        "role_used": role,
        "collection": f"Schema.{collection}",
        "compiled_mongo_filter": mongo_filter,
        "matched_count": len(docs),
        "results": docs,
    }