# Backend 0.8.0: навигация по действующим инструкциям

Эксплуатация и архитектура: [OPERATIONS.md](OPERATIONS.md). Полный разбор модулей:
[SCRIPT_REFERENCE.md](SCRIPT_REFERENCE.md). Пошаговые HTTP-этапы: раздел 23
[STUDENT_GUIDE.md](STUDENT_GUIDE.md).

Актуальный маршрут: HTTP → main.py → principals → модуль операции → общий MongoDB
коннектор → ответ. Синхронизация реализована в entities/layer_records, не в заглушке
sync.py. Консоль /v1/console использует mongo_console.py, не старый console.py.

GPKG: gpkg_uploads принимает блоки, gpkg_import преобразует строки, gpkg_jobs хранит
проверку и прогресс на диске и применяет все страницы. Общего предела 1000 строк/
32 МиБ нового файла нет. Ограничения шагов и значений приведены в общей инструкции.

Исторические проверки и этапы: [COMPREHENSIVE_FIXES.md](COMPREHENSIVE_FIXES.md),
[QGIS_HOTFIX_071.md](QGIS_HOTFIX_071.md). Они не заменяют текущую инструкцию.
