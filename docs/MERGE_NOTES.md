> Историческая инструкция предыдущей версии. Для текущего запуска и строгой загрузки используйте README.md и docs/BACKEND.md. Старое создание отдельных точек и частичный импорт отключены.

# Integration of main and secondary branches

Primary basis: `GIS-MongoDB-publish.zip`. Selected implementation modules from `DB_Whit_Kuznecov-main.zip` were overlaid on that basis.

## Integrated modules
- WSGI backend endpoints for `.gpkg` upload, queries, analytics and GeoJSON export
- Dashboard (Streamlit), QGIS helper files
- The secondary `model.json` with `Instances.instance` and `Foci.id_instance` (as supplied)
- Migration `rename-v7.js` handling those renames

## Important limitations
- `POST /v1/clear-cases` and the dashboard delete control are removed because the assignment forbids deleting original records.
- The imported GeoPackage parsing code from the secondary branch is not production-safe: it can impute missing coordinates, dates and ages. Do not use with actual case data before this is corrected.
- Spatial district tests in the secondary version use rectangular approximations, not authoritative boundaries. Results must not be represented as correct administrative polygon queries.
- QGIS point GUI, API and GeoPackage export are implemented in this version. See docs/QGIS.md.
- A merged source tree is not equivalent to a Docker-tested application. Run integration tests on a disposable environment before deployment.
- Fresh environment migration and existing volumes require explicit backup and review of schema/indexes.

No local `.env`, `.git` internals, datasets or database backups are included.
