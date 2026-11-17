# Воспроизведение измерений

Используйте отдельную одноразовую установку с пустой Schema, настроенными
ролями/индексами, backend и переменными окружения MongoDB. Рабочие volumes не
подключайте. Источники A/B не нужны: create_fixture генерирует 4000 связанных
записей, по 8192 байта дополнительного неиспользуемого текста в четырёх коллекциях.
Исторические неполные атрибуты специально допустимы моделью хранения; фикстура
не является примером обычного пользовательского strict-импорта.

```bash
python tests/performance/create_fixture.py --confirm-empty-disposable --rows 4000
python tests/performance/backend_benchmark.py --project /path/to/baseline --mode overview
python tests/performance/backend_benchmark.py --project /path/to/candidate --mode overview
python tests/performance/backend_benchmark.py --project /path/to/baseline --mode geometry
python tests/performance/backend_benchmark.py --project /path/to/candidate --mode geometry
python tests/performance/backend_benchmark.py --project /path/to/baseline --mode validation
python tests/performance/backend_benchmark.py --project /path/to/candidate --mode validation
QT_QPA_PLATFORM=offscreen /usr/bin/python3 tests/performance/qgis_benchmark.py --project /path/to/baseline
QT_QPA_PLATFORM=offscreen /usr/bin/python3 tests/performance/qgis_benchmark.py --project /path/to/candidate
```

`/usr/bin/python3` в примере — Python, в котором установлен PyQGIS; на вашей
машине путь может отличаться. Backend-измерения используют одинаковые данные
и по 500 строк на страницу. Один прогрев, три замера с tracemalloc, отдельно
один проход для размера BSON-ответов MongoDB. Память — пик выделений Python во
время вызова, не полный RSS процесса. QGIS измеряется отдельным процессом на
40000 синтетических строк, включает пик RSS с библиотеками, один замер на версию.

Проверка GPKG в benchmark создаёт только временные служебные задания, не применяет
их. Она использует 1003 строки Therapy со ссылкой на одного доступного Patient.
Для подтверждения одинакового результата overview/geometry сравнивайте sha256;
для validation — status и valid_rows, которые проверяет сам сценарий.

Нагрузка на новый API:

```bash
python tests/integration/load_http.py
```

Нужны QGIS_TEST_BACKEND и API-токены тестовой установки. 96 запросов, 4 потока,
три роли, endpoint коллекций/overview/statistics. Это короткий smoke-load, а не
длительный soak-тест или определение максимальной ёмкости. Сравнительная задержка
под такой нагрузкой для старого HTTP-сервера не измерялась. Сравнение до/после
охватывает отдельные пути backend/QGIS и описано в OPTIMIZATION_0100.md.

Сохранённые results.json/load_results.json относятся к проверенной поставке;
новые запуски могут дать другие времена. Никаких чужих пациентов/исходных файлов
в фикстуре нет. После проверки удаляйте только созданную вами одноразовую установку.
