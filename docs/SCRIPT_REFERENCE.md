# Справочник всех скриптов и модулей 0.8.0

Назначения сверены с маршрутизатором и местами вызовов. Наличие файла не означает, что он участвует в активном HTTP-пути. Код этой поставкой документации не изменяется. Все пути ниже отсчитываются от корня проекта.

## Как читать справочник

На хосте запускаются управляющие scripts/*.py. Backend-модули исполняются внутри приложения и не запускаются командой `python произвольный_файл.py`. Storage JS требуют mongosh/контейнерного контекста и административных переменных. QGIS-модули загружает сам QGIS. Tests/integration с записью предназначены только для одноразовой БД.

## Управление

| Файл | Назначение и путь данных | Запуск / влияние |
|---|---|---|
| [scripts/check_project.py](../scripts/check_project.py) | Читает Python/JS/JSON и проверяет синтаксис/обязательные файлы поставки. | На хосте; нужен Node.js. Не проверяет живую БД и не запускает QGIS. |
| [scripts/import_excel.py](../scripts/import_excel.py) | Обёртка запуска старого планировщика import_excel в контейнере excel-import; файл монтируется read-only. | План: py scripts/import_excel.py data/test_datasetA.xlsx --namespace test-dataset-a. Требует собранный образ; --apply направлен в отключённый legacy-ввод и не заменяет seed/GPKG. |
| [scripts/manage.py](../scripts/manage.py) | Главный CLI-диспетчер: .env, Compose, seed, проверки и обслуживание. Полная таблица действий — в практикуме. | На хосте: py scripts/manage.py <действие>. Часть действий меняет БД/конфигурацию; не является HTTP-сервером. |
| [scripts/package_plugin.py](../scripts/package_plugin.py) | Собирает исходники qgis_plugin в dist/qgis_mongodb.zip, исключая кеши и данные. | На хосте после правки плагина; меняет только ZIP. Затем переустановка и рестарт QGIS. |

## Backend: HTTP, права, данные

| Файл | Назначение и путь данных | Запуск / влияние |
|---|---|---|
| [backend/app/__init__.py](../backend/app/__init__.py) | Маркер Python-пакета; в этой версии пустой. | Импортируется автоматически; отдельной операции с данными нет. |
| [backend/app/auth/__init__.py](../backend/app/auth/__init__.py) | Маркер Python-пакета; в этой версии пустой. | Импортируется автоматически; отдельной операции с данными нет. |
| [backend/app/auth/ownership.py](../backend/app/auth/ownership.py) | Внутренние примитивы Principal/owner-scope и атомарного изменения по владельцу. | Не самостоятельная регистрация/логин. Активные HTTP-проверки реализованы также в principals и records/entities. |
| [backend/app/auth/principals.py](../backend/app/auth/principals.py) | Сопоставляет Bearer-токен, имя, роль и owner; поддерживает QGIS_IDENTITIES_JSON. | Вызывается main для /v1. Неверная пара имени/токена → 401; роль из тела не становится полномочием. |
| [backend/app/database/__init__.py](../backend/app/database/__init__.py) | Маркер Python-пакета; в этой версии пустой. | Импортируется автоматически; отдельной операции с данными нет. |
| [backend/app/database/mongodb.py](../backend/app/database/mongodb.py) | Единый PyMongo-коннектор: пять технических учётных записей, ограниченные пулы, готовность и закрытие клиентов. | Внутренний модуль backend; API admin использует прикладной доступ, а не выдаёт root клиенту. |
| [backend/app/main.py](../backend/app/main.py) | WSGI-диспетчер /health и /v1; авторизация, ограничения тела запроса, маршрутизация ошибок. | Docker CMD: python -m app.main из /app. До 8 одновременных HTTP-запросов; все пользовательские каналы проходят здесь. |
| [backend/app/models/__init__.py](../backend/app/models/__init__.py) | Маркер Python-пакета; в этой версии пустой. | Импортируется автоматически; отдельной операции с данными нет. |
| [backend/app/models/schema.py](../backend/app/models/schema.py) | Читает единственный model.json с локального пути или STORAGE_SCHEMA_PATH. | Внутренний модуль; не меняет схему, задаёт общий источник типов. |
| [backend/app/modules/__init__.py](../backend/app/modules/__init__.py) | Маркер Python-пакета; в этой версии пустой. | Импортируется автоматически; отдельной операции с данными нет. |
| [backend/app/modules/analytics.py](../backend/app/modules/analytics.py) | Учебные q4_timeseries/q5_group_age/q6_unwind по связанным строкам. | /v1/tz-query. Сейчас одна стандартная страница экспорта; Mongo pipeline в результате — иллюстрация, не доказательство исполнения по всей БД. |
| [backend/app/modules/console.py](../backend/app/modules/console.py) | Предыдущий AST-парсер ограниченного Python-синтаксиса. | Сохранён для совместимости/истории; текущий /v1/console вызывает mongo_console.py, а не этот файл. |
| [backend/app/modules/dashboard_stats.py](../backend/app/modules/dashboard_stats.py) | Агрегаты по доступной области и независимая карта до 5000 Geodata, кеш на 15 секунд. | /v1/statistics; не тот же путь, что полный cached_overview главного dashboard. |
| [backend/app/modules/entities.py](../backend/app/modules/entities.py) | Проверяет отдельные создаваемые сущности, типы, FK, owner; правки по ревизии и batch-транзакции. | main/импорт → create/edit/edit_batch. Поддерживает частичный набор GPKG; не удаляет документы. |
| [backend/app/modules/export_data.py](../backend/app/modules/export_data.py) | Собирает связанную страницу обращений по Instances/Foci/Patient/Therapy/адресам; возвращает next. | /v1/overview, /dashboard, /geojson. По умолчанию 500 обращений на страницу; полнота зависит от обхода next клиентом. |
| [backend/app/modules/geometry.py](../backend/app/modules/geometry.py) | Строгая нормализация новых WGS84 Point и терпимое чтение исторических значений; выдаёт GeoJSON/WKT. | Внутренний модуль. Read-адаптер не переписывает MongoDB; сохранённую пустую geometry исправляет отдельный JS. |
| [backend/app/modules/gpkg_import.py](../backend/app/modules/gpkg_import.py) | Каталог таблиц/поля, CRS и Point WKB, типизация сопоставления, PK-пагинация выбранных столбцов. | Внутренний преобразователь; build — потоковый диагностический итератор, production HTTP использует jobs. |
| [backend/app/modules/gpkg_jobs.py](../backend/app/modules/gpkg_jobs.py) | Хранит проверенные строки и прогресс в SQLite; проверяет все страницы, затем применяет строки MongoDB. | /v1/gpkg/jobs: start/status/validate/apply. ≤250 строк проверки, ≤25 записи, дополнительно байтовые границы; транзакция на строку. |
| [backend/app/modules/gpkg_uploads.py](../backend/app/modules/gpkg_uploads.py) | Дисковая chunk-передача, манифест, размер/SHA256/SQLite, повтор блока, срок и очистка служебного кеша. | /v1/gpkg/uploads; блок ≤4 МиБ, не размер всего файла. ROOT задан GPKG_UPLOAD_DIR. |
| [backend/app/modules/import_data.py](../backend/app/modules/import_data.py) | Заглушка старого невалидированного импорта. | Выдаёт отказ; не является действующим GPKG pipeline. |
| [backend/app/modules/import_excel.py](../backend/app/modules/import_excel.py) | Старый read-only планировщик XLSX; код нормализации сохранён, выполнение записи блокируется ранней проверкой store. | CLI --apply существует в разборе аргументов, но legacy partial import отклоняется. Для A+B используется seed_excel, для нового ввода — строгий API. |
| [backend/app/modules/mongo_console.py](../backend/app/modules/mongo_console.py) | Активный парсер Mongo/Python-литералов, read-операторы, безопасный lookup и курсоры результата. | main → /v1/console. Не eval/exec пользовательского кода; write pipelines запрещены, helper-ввод проверяет backend. |
| [backend/app/modules/qgis_data.py](../backend/app/modules/qgis_data.py) | Сохранённый point API: чтение/правка Geodata и общие ApiError/проверки для модулей. | main направляет /v1/qgis/points сюда, но POST одной точки запрещён до вызова execute. Основной многоколлекционный UI использует records/entities. |
| [backend/app/modules/query.py](../backend/app/modules/query.py) | Предыдущий структурный обработчик JSON/XML. | Остаток старого пути; main импортирует модуль, но актуальный /v1/query направлен в query_api. Не считать импорт вызовом execute. |
| [backend/app/modules/query_api.py](../backend/app/modules/query_api.py) | Активный структурный JSON/XML-парсер dashboard: поля/операторы/role scope, результат с limit 1–200. | /v1/query; ограниченная форма, не полная пагинация Mongo-консоли. |
| [backend/app/modules/records.py](../backend/app/modules/records.py) | Каталог/страницы 17 коллекций, BSON и _key, области доступа, строгий полный набор, автоссылки. | main → catalog/page/create; до 200 строк страницы, а не предел коллекции. Полный ввод — транзакция. |
| [backend/app/modules/seed.py](../backend/app/modules/seed.py) | Точка начальной загрузки A+B: manifest, SHA256, маркеры cases, вызовы загрузчиков. | Автоматически при up в excel-import: python -m app.modules.seed. Пишет историю и метки загрузки. |
| [backend/app/modules/seed_b.py](../backend/app/modules/seed_b.py) | Insert-only преобразование встроенной части B с детерминированными ID и связями. | Вызывает seed.py; отсутствующие паспорт/возраст не выдумываются. Не сервер загрузки произвольного JSON. |
| [backend/app/modules/seed_excel.py](../backend/app/modules/seed_excel.py) | Читает встроенный XLSX, архивирует исходные строки, нормализует таблицы и вставляет отсутствующие _id. | Вызывает seed.py; отдельный CLI file --namespace ... [--apply] — административный bootstrap, не пользовательский обход правил. |
| [backend/app/modules/spatial.py](../backend/app/modules/spatial.py) | Учебные q1_polygon/q2_nearest/q3_periods: область, расстояния, периоды. | /v1/tz-query для reader. Сейчас читает одну страницу export_data; полигонный учебный сценарий использует заданные bounding boxes, не универсальный серверный GIS-анализ. |
| [backend/app/modules/sync.py](../backend/app/modules/sync.py) | Резервная заглушка execute с NotImplementedError. | Не участвует в текущей синхронизации. Реальные правки: layer_records → main → entities. |

## Подготовка MongoDB

| Файл | Назначение и путь данных | Запуск / влияние |
|---|---|---|
| [storage/init/bootstrap.js](../storage/init/bootstrap.js) | Явно загружает schema → roles → indexes при первоначальной инициализации пустой MongoDB. | Единственный entrypoint-init JS; на уже заполненном data-томе повтор не заменяет provision. |
| [storage/init/indexes.js](../storage/init/indexes.js) | Создаёт/проверяет индексы схемы/владельца. | bootstrap/provision. Пространственный partial index отдельно подготавливает geospatial-index.js. |
| [storage/init/roles.js](../storage/init/roles.js) | Применяет спецификацию ролей и технических аккаунтов; сохраняет существующие пароли. | bootstrap/provision. Расхождение паролей старого .env нельзя лечить новым init. |
| [storage/init/schema.js](../storage/init/schema.js) | Нормализует model.json, создаёт/сверяет коллекции и валидаторы. | bootstrap/provision в mongosh; не пользовательский конструктор произвольной схемы. |
| [storage/migrations/rename-v7.js](../storage/migrations/rename-v7.js) | План/применение миграции старых опечаток имён с проверкой коллизий и сохранением значений. | manage.py migrate-plan/migrate; это не обязательный ежедневный импорт, нужен отдельный план/копия. |
| [storage/scripts/admin.js](../storage/scripts/admin.js) | Подключается к admin по контейнерным env и назначает контекст Schema. | Вспомогательный load для административных JS; сам по себе не проверяет всю систему. |
| [storage/scripts/backfill-geometry.js](../storage/scripts/backfill-geometry.js) | Прежний узкий backfill только для отсутствующей geometry с числовыми координатами. | Сохранён как старый административный инструмент; штатная geometry использует расширенный geospatial-index.js. |
| [storage/scripts/entrypoint.sh](../storage/scripts/entrypoint.sh) | Создаёт replica.key в config-томе, задаёт владельца/права, передаёт запуск официальному Mongo entrypoint. | Docker entrypoint storage. Не удалять ключ при обновлении и не публиковать config-том. |
| [storage/scripts/geospatial-index.js](../storage/scripts/geospatial-index.js) | Восстанавливает пустую geometry по корректным координатам, сохраняет прежнее значение, помечает валидность, создаёт partial 2dsphere. | manage.py geometry/provision/up; меняет только соответствующие геометрические/служебные поля, не произвольные данные. |
| [storage/scripts/health.js](../storage/scripts/health.js) | Проверяет окончательный mongod и ping без поиска пользователей/схем. | Docker healthcheck storage. Healthy не означает успешный verify/seed. |
| [storage/scripts/provision.js](../storage/scripts/provision.js) | Оркестратор replica → schema → roles → indexes → geospatial-index. | manage.py provision/up; storage уже должен запускаться. |
| [storage/scripts/replica.js](../storage/scripts/replica.js) | Инициализирует/проверяет rs0 и ждёт PRIMARY. | provision; административная подготовка транзакций, не отказоустойчивый кластер из нескольких узлов. |
| [storage/scripts/role-spec.js](../storage/scripts/role-spec.js) | Единая спецификация ролей/аккаунтов для настройки и проверки. | load из roles/verify; исключения guest перечислены явно, не wildcard. |
| [storage/scripts/schema-tools.js](../storage/scripts/schema-tools.js) | Чистые общие функции нормализации/сравнения схем и индексов. | load из других JS; не самостоятельное создание данных. |
| [storage/scripts/verify.js](../storage/scripts/verify.js) | Проверяет авторизацию, валидаторы, cases, точные grants, подключения и индексы. | manage.py verify/up; read-only проверка, печатает PASS/FAIL и код завершения. |

## Плагин QGIS

| Файл | Назначение и путь данных | Запуск / влияние |
|---|---|---|
| [qgis_plugin/__init__.py](../qgis_plugin/__init__.py) | classFactory — точка регистрации QGIS; возвращает MongodbDataLoader. | Автоматически менеджером модулей QGIS; не запускать обычным Python. |
| [qgis_plugin/api_client.py](../qgis_plugin/api_client.py) | Асинхронный HTTP-клиент через QgsNetworkAccessManager: URL, токен/имя, таймаут и обработка ответа. | Работает в QGIS с его proxy-настройками; не открывает PyMongo-клиент на настольном компьютере. |
| [qgis_plugin/console_dialog.py](../qgis_plugin/console_dialog.py) | Редактор пользовательского текста, примеры, результаты, ошибки, продолжение курсора. | Отправляет текст /v1/console; не выполняет host Python. |
| [qgis_plugin/geometry_compat.py](../qgis_plugin/geometry_compat.py) | Декодирует подготовленные WKT/GeoJSON совместимым QGIS API без вызова geometryFromGeoJson 3.36+. | Без CRS-преобразований; слой получает уже нормализованные backend координаты. |
| [qgis_plugin/gpkg_dialog.py](../qgis_plugin/gpkg_dialog.py) | Выбор файла, chunk upload, сопоставление, автоматическая полная проверка, пакетная запись и resume. | QSettings хранит job_id/метаданные файла для подключения, не API-токен. Работает с новыми uploads/jobs. |
| [qgis_plugin/guarded_memory.py](../qgis_plugin/guarded_memory.py) | Тонкий provider поверх memory cache, разрешающий локальную фиксацию лишь после подтверждения backend. | Регистрируется программно. Держит Python-объекты; отказ provider сохраняет edit buffer. Не постоянный MongoDB provider. |
| [qgis_plugin/gui/__init__.py](../qgis_plugin/gui/__init__.py) | Маркер Python-пакета; в этой версии пустой. | Импортируется автоматически; отдельной операции с данными нет. |
| [qgis_plugin/layer_records.py](../qgis_plugin/layer_records.py) | Строит типизированный слой/таблицу и связывает обычный QGIS commit с backend batch. | Включая пустые таблицы и Point; ошибки сохраняют локальный буфер, успех обновляет ревизию/геометрию. |
| [qgis_plugin/layer_sync.py](../qgis_plugin/layer_sync.py) | Старый преобразователь страницы point API и экспорт point-слоя. | Путь базового старого интерфейса; актуальная многоколлекционная загрузка идёт через layer_records. |
| [qgis_plugin/mongodb_data_loader.py](../qgis_plugin/mongodb_data_loader.py) | Регистрирует меню/кнопку, локализацию и окно исходного Data Loader, удаляет UI при unload. | Вызовы QGIS initGui/run/unload; не выполняет преобразование геометрии. |
| [qgis_plugin/mongodb_data_loader_dialog.py](../qgis_plugin/mongodb_data_loader_dialog.py) | Основное окно: подключение, смена профиля, каталог, выбор коллекций, переход к записи/консоли/GPKG. | Вызывает RecordsDialog и API; при смене credentials инвалидирует старые запросы и управляемые слои. |
| [qgis_plugin/plugin.py](../qgis_plugin/plugin.py) | Базовые формы PointDialog, общий клиент/настройки и сохранённый старый point-only UI. | RecordsDialog наследует общие функции и переопределяет бизнес-операции. Текущая classFactory не регистрирует второй старый плагин. |
| [qgis_plugin/records_dialog.py](../qgis_plugin/records_dialog.py) | Полный обход страниц выбранной коллекции, замена её слоя, формы создания/JSON-правок и привязка сессии. | Главный UI-путь 17 коллекций. Не останавливается после одной страницы; вызовы backend строго авторизуются. |

## Dashboard

| Файл | Назначение и путь данных | Запуск / влияние |
|---|---|---|
| [dashboard/app.py](../dashboard/app.py) | Вход по ролям, API-клиент, полный cached_overview аналитика, вкладки и фильтры/консоль/экспорт. | Streamlit в контейнере dashboard. Не содержит прямого пользовательского MongoDB-соединения. |
| [dashboard/components/__init__.py](../dashboard/components/__init__.py) | Маркер Python-пакета; в этой версии пустой. | Импортируется автоматически; отдельной операции с данными нет. |
| [dashboard/components/charts.py](../dashboard/components/charts.py) | Графики по переданной фильтрованной выборке. | Не отдельная полная серверная агрегация и не импорт. |
| [dashboard/components/filters.py](../dashboard/components/filters.py) | Фильтры загруженных связанных строк. | Вызывает dashboard/app.py; фильтр изменяет отображаемую выборку, не документы БД. |
| [dashboard/components/maps.py](../dashboard/components/maps.py) | Карта PyDeck: кластеры всех переданных геозаписей либо ограниченный экранный набор отдельных точек. | Экранный слайдер не предел хранения/импорта. Неверные координаты не рисуются. |

## Учебные запросы

| Файл | Назначение и путь данных | Запуск / влияние |
|---|---|---|
| [queries/queries.mongosh.js](../queries/queries.mongosh.js) | Читаемые 100 адаптированных запросов с фиксированной AS_OF. | Только в контролируемом контексте mongosh; не вставлять весь файл в безопасную одновыраженческую консоль плагина. |
| [queries/run.mongosh.js](../queries/run.mongosh.js) | Запускает утверждённый каталог через QUERY_CATALOG/QUERY_OUTPUT/QUERY_AS_OF, сохраняет EJSON результаты. | Административный учебный runner; использует new Function для доверенного каталога, не для произвольного ввода. API-консоль так не исполняет код. |
| [queries/verify_results.py](../queries/verify_results.py) | Независимо вычисляет планы каталога на BSON-снимке и сравнивает результаты. | Отдельная контрольная процедура с подготовленными входами; не проверка текущей изменённой БД из одного клика. |

## Проверочные сценарии

| Файл | Назначение и путь данных | Запуск / влияние |
|---|---|---|
| [tests/__init__.py](../tests/__init__.py) | Маркер Python-пакета; в этой версии пустой. | Импортируется автоматически; отдельной операции с данными нет. |
| [tests/e2e/__init__.py](../tests/e2e/__init__.py) | Маркер Python-пакета; в этой версии пустой. | Импортируется автоматически; отдельной операции с данными нет. |
| [tests/e2e/test_pipeline.py](../tests/e2e/test_pipeline.py) | Исторический шаблон E2E с unittest.skip и устаревшим текстом Storage-этапа. | Пропущенный тест не подтверждает сквозную работу и не означает отсутствия нынешних модулей. Фактические проверки — в отчёте 0.8.0. |
| [tests/integration/__init__.py](../tests/integration/__init__.py) | Маркер Python-пакета; в этой версии пустой. | Импортируется автоматически; отдельной операции с данными нет. |
| [tests/integration/bulk_qgis.py](../tests/integration/bulk_qgis.py) | Реальное окно: файл 43589632 байта/5003 строки, закрытие диалога, resume, повтор, ошибка строки 5003. | Не общий запуск production. Нужны подготовленная одноразовая среда/токены, а для Qt — PyQGIS. См. входные переменные в начале файла. |
| [tests/integration/bulk_resume_http.py](../tests/integration/bulk_resume_http.py) | Три фазы prepare/partial/finish одного задания между отдельными перезапусками backend; создаёт 1003 Geodata. | Не общий запуск production. Нужны подготовленная одноразовая среда/токены, а для Qt — PyQGIS. См. входные переменные в начале файла. |
| [tests/integration/comprehensive_http.py](../tests/integration/comprehensive_http.py) | Полная пагинация/консоль/права и интерактивные правки/импорты на одноразовой базе A+B. | Не общий запуск production. Нужны подготовленная одноразовая среда/токены, а для Qt — PyQGIS. См. входные переменные в начале файла. |
| [tests/integration/comprehensive_qgis.py](../tests/integration/comprehensive_qgis.py) | Загрузка 17 коллекций, экспорт GPKG, сохранение правок и переключение ролей в PyQGIS. | Не общий запуск production. Нужны подготовленная одноразовая среда/токены, а для Qt — PyQGIS. См. входные переменные в начале файла. |
| [tests/integration/dashboard_render.py](../tests/integration/dashboard_render.py) | Streamlit AppTest трёх ролей, вкладок/фильтров/журнала и JSON/XML-консоли через backend. | Не общий запуск production. Нужны подготовленная одноразовая среда/токены, а для Qt — PyQGIS. См. входные переменные в начале файла. |
| [tests/integration/excel_dashboard.py](../tests/integration/excel_dashboard.py) | Связи исходного Excel и отдача dashboard в тестовом окружении. | Не общий запуск production. Нужны подготовленная одноразовая среда/токены, а для Qt — PyQGIS. См. входные переменные в начале файла. |
| [tests/integration/gpkg_fixture.py](../tests/integration/gpkg_fixture.py) | Создаёт маленький учебный SQLite GPKG EPSG:3857 и mapping; вспомогательный генератор, не импортёр пользователя. | Не общий запуск production. Нужны подготовленная одноразовая среда/токены, а для Qt — PyQGIS. См. входные переменные в начале файла. |
| [tests/integration/gpkg_rejections.py](../tests/integration/gpkg_rejections.py) | Отрицательные live-проверки: обязательность/CRS/FK/типы/подмена таблицы/guest; проверяет отсутствие побочных записей. | Не общий запуск production. Нужны подготовленная одноразовая среда/токены, а для Qt — PyQGIS. См. входные переменные в начале файла. |
| [tests/integration/hotfix_ui_state.py](../tests/integration/hotfix_ui_state.py) | Автономный Qt-тест с fake API: старый decoder, устаревшие callbacks, ошибки и блокировка кнопки; БД не использует. | В PyQGIS, автономно без MongoDB. Обычный Python хоста может не иметь qgis. |
| [tests/integration/hotfix_workflows.py](../tests/integration/hotfix_workflows.py) | Живые запросы из окна консоли и автоматическая проверка/запись частичного GPKG. | Не общий запуск production. Нужны подготовленная одноразовая среда/токены, а для Qt — PyQGIS. См. входные переменные в начале файла. |
| [tests/integration/http_probe.py](../tests/integration/http_probe.py) | HTTP-проверка контейнерного backend в отдельном Docker integration-проекте. | Не общий запуск production. Нужны подготовленная одноразовая среда/токены, а для Qt — PyQGIS. См. входные переменные в начале файла. |
| [tests/integration/integrated_ui.py](../tests/integration/integrated_ui.py) | Файл → mapping → validate → apply → повтор в настоящем Qt-диалоге. | Не общий запуск production. Нужны подготовленная одноразовая среда/токены, а для Qt — PyQGIS. См. входные переменные в начале файла. |
| [tests/integration/legacy.js](../tests/integration/legacy.js) | Контролируемые фикстуры старых названий для миграции; требует ISOLATED_STORAGE_TEST и FIXTURE_ACTION. | Не общий запуск production. Нужны подготовленная одноразовая среда/токены, а для Qt — PyQGIS. См. входные переменные в начале файла. |
| [tests/integration/native_records.py](../tests/integration/native_records.py) | Опциональный native runner с MONGOD_BINARY/MONGOSH_BINARY/QGIS_PYTHON и собственной временной БД. | Не общий запуск production. Нужны подготовленная одноразовая среда/токены, а для Qt — PyQGIS. См. входные переменные в начале файла. |
| [tests/integration/network.js](../tests/integration/network.js) | MongoDB network/auth probe; READ_ONLY вне тестового режима, запись разрешается TEST_WRITES только в изолированном тесте. | Не общий запуск production. Нужны подготовленная одноразовая среда/токены, а для Qt — PyQGIS. См. входные переменные в начале файла. |
| [tests/integration/persistence.js](../tests/integration/persistence.js) | Проверяет сохранность тестовых данных после restart storage; ожидает предварительные фикстуры. | Не общий запуск production. Нужны подготовленная одноразовая среда/токены, а для Qt — PyQGIS. См. входные переменные в начале файла. |
| [tests/integration/qgis_actions.py](../tests/integration/qgis_actions.py) | Qt-сценарии базовых действий point-интерфейса; часть ранних регрессий. | Не общий запуск production. Нужны подготовленная одноразовая среда/токены, а для Qt — PyQGIS. См. входные переменные в начале файла. |
| [tests/integration/qgis_http.py](../tests/integration/qgis_http.py) | Проверки point HTTP API; это не GUI QGIS и не доказательство загрузки всех коллекций. | Не общий запуск production. Нужны подготовленная одноразовая среда/токены, а для Qt — PyQGIS. См. входные переменные в начале файла. |
| [tests/integration/records_http.py](../tests/integration/records_http.py) | Live-проверки строгого набора/прав/ревизий и вспомогательные HTTP-функции; пишет тестовые данные. | Не общий запуск production. Нужны подготовленная одноразовая среда/токены, а для Qt — PyQGIS. См. входные переменные в начале файла. |
| [tests/integration/records_qgis.py](../tests/integration/records_qgis.py) | PyQGIS регрессия форм/таблиц связанных записей; только одноразовая БД. | Не общий запуск production. Нужны подготовленная одноразовая среда/токены, а для Qt — PyQGIS. См. входные переменные в начале файла. |
| [tests/integration/seed_ui.py](../tests/integration/seed_ui.py) | UI-проверка seed/слоёв в подготовленной тестовой среде. | Не общий запуск production. Нужны подготовленная одноразовая среда/токены, а для Qt — PyQGIS. См. входные переменные в начале файла. |
| [tests/unit/__init__.py](../tests/unit/__init__.py) | Маркер Python-пакета; в этой версии пустой. | Импортируется автоматически; отдельной операции с данными нет. |
| [tests/unit/migration.cjs](../tests/unit/migration.cjs) | JS mock планирования/применения/коллизий миграции. | Через manage.py test; JS .cjs — с Node.js, Python — unittest. Нет обращения к рабочей БД; временные файлы/моки допустимы. |
| [tests/unit/static.cjs](../tests/unit/static.cjs) | JS mock начальной схемы/ролей/повторной настройки. | Через manage.py test; JS .cjs — с Node.js, Python — unittest. Нет обращения к рабочей БД; временные файлы/моки допустимы. |
| [tests/unit/test_comprehensive.py](../tests/unit/test_comprehensive.py) | Mongo-синтаксис, pipeline security, BSON/старые ID, частичные сущности и привязка имени к токену. | Через manage.py test; JS .cjs — с Node.js, Python — unittest. Нет обращения к рабочей БД; временные файлы/моки допустимы. |
| [tests/unit/test_excel.py](../tests/unit/test_excel.py) | Старый read-only Excel-план и отказ legacy apply. | Через manage.py test; JS .cjs — с Node.js, Python — unittest. Нет обращения к рабочей БД; временные файлы/моки допустимы. |
| [tests/unit/test_geometry.py](../tests/unit/test_geometry.py) | Нормализация Point и конфликты координат. | Через manage.py test; JS .cjs — с Node.js, Python — unittest. Нет обращения к рабочей БД; временные файлы/моки допустимы. |
| [tests/unit/test_gpkg.py](../tests/unit/test_gpkg.py) | Структура GPKG, CRS, типы, обязательность и идентичность повторов. | Через manage.py test; JS .cjs — с Node.js, Python — unittest. Нет обращения к рабочей БД; временные файлы/моки допустимы. |
| [tests/unit/test_gpkg_batches.py](../tests/unit/test_gpkg_batches.py) | Реальный SQLite/disk: 1003 строки, составные PK, поздняя ошибка, restart/retry, байтовые страницы, кеш и UTF8. | Через manage.py test; JS .cjs — с Node.js, Python — unittest. Нет обращения к рабочей БД; временные файлы/моки допустимы. |
| [tests/unit/test_hotfix.py](../tests/unit/test_hotfix.py) | Пользовательский синтаксис/regex, историческая геометрия, NULL-сущности, версия backend. | Через manage.py test; JS .cjs — с Node.js, Python — unittest. Нет обращения к рабочей БД; временные файлы/моки допустимы. |
| [tests/unit/test_portability.py](../tests/unit/test_portability.py) | Переносимость поставки, пути и конфигурация. | Через manage.py test; JS .cjs — с Node.js, Python — unittest. Нет обращения к рабочей БД; временные файлы/моки допустимы. |
| [tests/unit/test_query_api.py](../tests/unit/test_query_api.py) | JSON/XML query API и разграничение доступа. | Через manage.py test; JS .cjs — с Node.js, Python — unittest. Нет обращения к рабочей БД; временные файлы/моки допустимы. |
| [tests/unit/test_records.py](../tests/unit/test_records.py) | Строгий полный набор, схемы, авторизация и операции записей. | Через manage.py test; JS .cjs — с Node.js, Python — unittest. Нет обращения к рабочей БД; временные файлы/моки допустимы. |
| [tests/unit/test_repairs.py](../tests/unit/test_repairs.py) | Связи, новые роли/схема, миграционные исправления. | Через manage.py test; JS .cjs — с Node.js, Python — unittest. Нет обращения к рабочей БД; временные файлы/моки допустимы. |
| [tests/unit/test_seed.py](../tests/unit/test_seed.py) | Manifest/SHA256/namespace встроенного источника. | Через manage.py test; JS .cjs — с Node.js, Python — unittest. Нет обращения к рабочей БД; временные файлы/моки допустимы. |
| [tests/unit/test_seed_b.py](../tests/unit/test_seed_b.py) | Нормализация B, связи и повторная загрузка. | Через manage.py test; JS .cjs — с Node.js, Python — unittest. Нет обращения к рабочей БД; временные файлы/моки допустимы. |
| [tests/unit/test_storage.py](../tests/unit/test_storage.py) | CLI/коннектор, конфигурация, пароли, readiness и безопасные команды. | Через manage.py test; JS .cjs — с Node.js, Python — unittest. Нет обращения к рабочей БД; временные файлы/моки допустимы. |
| [tests/unit/verify.cjs](../tests/unit/verify.cjs) | JS mock точности проверки grants, валидаторов, индексов/TTL. | Через manage.py test; JS .cjs — с Node.js, Python — unittest. Нет обращения к рабочей БД; временные файлы/моки допустимы. |

## Связанные файлы, которые не являются скриптами

| Файл | Назначение |
|---|---|
| docker-compose.yml | Сервисы, образы, сети, healthchecks, секреты из .env и три именованных тома. |
| docker-compose.local.yml | Публикация backend:8000/dashboard:8501 только на 127.0.0.1; tmpfs dashboard. |
| docker-compose.emergency.yml | Дополнительный локальный порт MongoDB через --emergency; не штатный путь QGIS. |
| docker-compose.compass.yml | Ручной отдельный overlay для Compass с localhost:27018; manage.py сам его не подмешивает. Не суммировать бездумно с emergency. |
| tests/integration/docker-compose.test.yml | Probe-сервисы и mounts для изолированных интеграционных проверок. |
| tests/integration/docker-compose.disposable.yml | Отдельные тестовые имена/режим томов; не рабочая установка. |
| backend/Dockerfile, dashboard/Dockerfile | Сборка отдельных runtime-образов; не исполняются напрямую в PowerShell. |
| backend/requirements.txt, dashboard/requirements.txt | Фиксированные Python-зависимости соответствующего контейнера. |
| storage/schema/model.json | BSON-схема 17 коллекций; менять только осознанной административной процедурой. |
| storage/config/mongod.conf | Настройки mongod: auth, сеть, WiredTiger и диагностика. Размер кеша дополнительно задаёт Compose CLI. |
| data/manifest.json | Имя/SHA256/namespace A, сведения части B. |
| data/test_datasetA.xlsx, data/testB_normalized.json | Неизменённые встроенные источники; не выход пользовательского импорта. |
| .env.example | Незаполненный шаблон состава параметров; не рабочие пароли. |
| qgis_plugin/metadata.txt, icon.png, INTEGRATION.txt | Версия/совместимость/оформление и предыдущие интеграционные заметки. |
| queries/catalog.json, results.json, RESULTS.md | Доверенный каталог и сохранённые результаты на исходном снимке/дате; не live-статистика текущей БД. |
| .github/workflows/checks.yml | CI: Python/Node-проверки на нескольких ОС и отдельный Docker integration job. Наличие workflow не является журналом успешного запуска. |
| docs/diagrams/*.dot и source_counts.csv | Редактируемые источники схем/графика этой инструкции; не runtime проекта. SVG в docs/assets не требует сетевого рендера. |
| docs/MANUAL.html | Автономная читаемая версия руководств с встроенными схемами, без серверной части. |
| tests/*VERIFICATION.md | История реально выполненных проверок. Актуальная программная версия — GPKG_BULK_080_VERIFICATION.md. |

## Точные точки входа

Ввод коллекций: `classFactory → MongodbDataLoader → MongodbDataLoaderDialog → RecordsDialog.load_all → GisApiClient → main → principals → records.page → MongoDB → layer_records`.

Новый GPKG: `GpkgDialog → uploads → gpkg_uploads → context/row_record → gpkg_jobs.validate → disk staging → gpkg_jobs.apply → entities.create/records.create → MongoDB`.

Правка: `beforeCommitChanges → layer_records → POST batch → entities.edit_batch → patch/revision/FK → transaction → подтверждение → GuardedMemory`.

История: `manage.up → excel-import → seed.main → manifest/SHA256/cases marker → seed_excel/seed_b → insert_missing → MongoDB → geospatial-index`.

## Проверка полноты справочника

Учтено **113** файлов с расширениями .py, .js, .cjs, .sh, включая пустые __init__.py. Для каждого указан режим использования. Операционные команды и ожидаемые результаты раскрыты в [практикуме](STUDENT_GUIDE.md).
