# Единый источник схемы

Схема хранится только в `storage/schema/model.json`. `schema.py` читает её из дерева проекта либо из пути STORAGE_SCHEMA_PATH внутри контейнера. Compose монтирует тот же каталог read-only в backend. Копий model.v6.json и storage_schema.json больше нет. Историю следует хранить в Git; миграция имён не требует старой полной схемы.
