# Историческая техническая справка Storage

Этот текст описывает прежний этап. Текущая QGIS-интеграция, маршруты /v1/qgis и установка плагина описаны в [QGIS.md](QGIS.md). В объединённой версии также присутствуют импорт и аналитические маршруты с ограничениями из MERGE_NOTES.md.

# GIS-MongoDB

Учебный проект хранилища MongoDB для пространственных и связанных предметных данных. Редакция 8: исправления диагностики, единая схема и переносимый запуск. Предел памяти основных контейнеров — 4,25 GiB, ниже ограничения проекта в 10 ГБ; ОС и Docker требуют дополнительную память.

**Реализовано:** Storage, валидаторы 17 предметных коллекций и первичная коллекция cases, индексы, роли, диагностический backend, проверка владельца документа внутри Python, миграция старых имён, локальные и контейнерные тесты.

**Ещё не реализовано:** пользовательский вход, полноценный API запросов/импорта/экспорта, обработка QGIS Core, dashboard, устанавливаемый QGIS-плагин, автоматическая синхронизация и хэширование проекта. Заготовки явно возвращают NotImplementedError или HTTP 501. Настоящее выполнение всего ETL-процесса пока невозможно.

[Инструкция студентам](docs/STUDENT_GUIDE.md) · [Обновление существующей базы](docs/UPGRADE.md) · [Отчёт о проверках](tests/VERIFICATION.md)

## Исправления

- `getRole(..., {showPrivileges: true})`: MongoDB действительно возвращает права, которые сравнивает verify. Административная роль создаётся в admin.
- Общие функции вынесены в schema-tools.js: больше нет отдельных несогласованных блоков keys/canonical/requireIndex. Тест исполняет настоящий verify.js.
- Индексы проверяются с учётом порядка полей, скрытых/частичных/разреженных индексов; проверяются также ссылочные индексы, валидатор cases и запрет TTL.
- unittest запускается с явным `-t` и полным набором файлов `__init__.py`. Ошибка неполной распаковки объясняется до запуска тестов.
- Единственный исходный файл схемы — storage/schema/model.json. Удалены model.v6.json и копия backend/app/models/storage_schema.json. Backend читает тот же файл через read-only mount; историю хранит Git.
- Настройки управляющего скрипта согласованы с Compose: выбранный .env имеет приоритет над унаследованными переменными проекта. Чтение учитывает UTF-8 BOM и CRLF Windows. Команды передаются как массив аргументов без shell.
- Отдельный override с управляемыми тестовыми volumes применяется только к временному интеграционному проекту. Обычная сетевая проверка не меняет тип рабочих volumes.
- Увеличен таймаут HTTP-healthcheck с учётом пяти подключений. Запуск backend после verify использует --no-deps, чтобы повторно не пересоздать уже проверенный Storage.
- Убраны одинаковые заглушки QGIS/dashboard: сохранены отдельные понятные контракты будущих компонентов без имитации готового функционала.

## Поддерживаемые среды

| Хост | Требования | Команда Python |
|---|---|---|
| Windows 10/11 | Docker Desktop, WSL2, режим Linux containers; Python 3.10+ | `py` |
| macOS, Intel или Apple Silicon | Docker Desktop; Python 3.10+ | `python3` |
| Linux x86-64/ARM64 | Docker Engine и Compose v2; Python 3.10+ | `python3` |

Контейнеры Linux на всех трёх хостах. Пути /opt и /proc находятся **внутри контейнеров** и не требуют аналогичных каталогов Windows. Архитектура platform не закреплена: Docker выбирает подходящий вариант официального образа. Процессор должен поддерживаться MongoDB 8.0; старые CPU могут быть несовместимы. ARM64 и Docker Desktop в этой среде не испытывались.

Node.js 22+ нужен для локальных JS-тестов, но не для обычного запуска контейнеров. PyMongo устанавливается при сборке backend; для локальных unit-тестов pip install не требуется. Compose должен поддерживать `up --wait`. Проверить окружение: `py scripts/manage.py doctor` (на Linux/macOS замените py на python3).

## Новый запуск

Распакуйте весь архив либо клонируйте репозиторий. Перейдите в корень GIS-MongoDB — каталог с docker-compose.yml. В PowerShell:

```powershell
py scripts/manage.py init
py scripts/manage.py volumes
py scripts/manage.py config --connections --local-api
py scripts/manage.py up --connections --local-api
py scripts/manage.py verify
py scripts/manage.py network-test
```

Linux/macOS:

```bash
python3 scripts/manage.py init
python3 scripts/manage.py volumes
python3 scripts/manage.py config --connections --local-api
python3 scripts/manage.py up --connections --local-api
python3 scripts/manage.py verify
python3 scripts/manage.py network-test
```

`init` создаёт .env и шесть случайных паролей, не перезаписывая существующий файл. `volumes` — явное создание томов для новой установки. По умолчанию сохранены имена старого проекта: gis_data_<случайный суффикс> и gis_config_<случайный суффикс>. При обновлении проверяйте реальные тома, не создавайте новую пустую базу вместо старой.

`up` останавливает backend, ждёт окончательный mongod, применяет роли, выполняет verify и только затем запускает backend. Без --connections работает только Storage. Параметры публикации портов нужно указывать при каждом up. Локальная диагностика доступна по http://127.0.0.1:8000/health/live и /health/ready.

## Команды

| Команда manage.py | Результат |
|---|---|
| init | Создание нового .env |
| configure | Добавление отсутствующих USER_PASSWORD/GUEST_PASSWORD без смены остальных паролей |
| doctor | Python/Node/Docker/Compose, ОС и архитектура Docker; секреты не выводятся |
| volumes | Явное создание отсутствующих рабочих volumes |
| config | Проверка Compose без печати паролей |
| up | Последовательный запуск и проверка |
| status / logs | Состояние сервисов / последние логи Storage |
| verify | Проверка схемы, ролей, индексов и доступа |
| provision | Создание отсутствующих пользователей, обновление назначений ролей |
| migrate-plan / migrate | План / применение переименований и текущей схемы |
| network-test | Чтение из отдельного контейнера, без записи |
| test | Python и JS-проверки без настоящего MongoDB |
| integration | Настоящие Docker-тесты в отдельном случайно названном проекте |
| stop | Остановка backend и Storage с сохранением данных |
| plan | Адреса компонентов и степень реализации |

Поддерживаемый формат .env: UTF-8, KEY=value, комментарии отдельной строкой. Значения с `$` заключайте в одинарные кавычки. Интерполяция `${...}`, двойные кавычки, повторные ключи и комментарии после значения намеренно не поддерживаются управляющим скриптом: такие строки вызывают понятную ошибку без раскрытия значения. Генерируемые hex-пароли не требуют кавычек. На Windows режим файла 0600 не заменяет настройку NTFS ACL.

## Архитектура и файлы

| Путь | Назначение |
|---|---|
| docker-compose.yml | Storage, необязательный backend, заготовка dashboard; лимиты и внутренние сети |
| docker-compose.local.yml / emergency.yml | Backend / MongoDB только на localhost хоста |
| scripts/manage.py | Переносимый CLI; Docker вызывается без shell |
| scripts/check_project.py | Синтаксис Python/JS, JSON и полнота поставки |
| storage/schema/model.json | Единственная предметная схема |
| storage/init/bootstrap.js | Первая инициализация: schema → roles → indexes |
| storage/init/schema.js | Создание коллекций и обновление валидаторов |
| storage/init/roles.js | Права и аккаунты, без неявной смены паролей |
| storage/init/indexes.js | Создание индексов из общего определения |
| storage/scripts/schema-tools.js | Нормализация схемы, индексы и сравнение прав |
| storage/scripts/role-spec.js | Определения ролей и аккаунтов |
| storage/scripts/admin.js / provision.js | Административное подключение / применение ролей |
| storage/scripts/health.js / verify.js | Доступность процесса / содержательная проверка хранилища |
| storage/migrations/rename-v7.js | Совместимость со старыми названиями; сохранённый номер миграции не означает старую схему |
| backend/app/database/mongodb.py | Пять ограниченных пулов PyMongo |
| backend/app/auth/ownership.py | Примитивы прав на отдельный документ |
| backend/app/models/schema.py | Загрузка единственной схемы |
| backend/app/main.py | Только HTTP-диагностика |
| backend/app/modules/ | Контракты будущих вычислений и ETL |
| dashboard/, qgis_plugin/ | Явные заготовки будущих интерфейсов |
| tests/unit/, integration/, e2e/ | Локальные, контейнерные и будущие сквозные проверки |
| .github/workflows/checks.yml | Unit/JS на трёх ОС; настоящие Docker-тесты на Ubuntu |

MongoDB хранит BSON, а не SQL-таблицы. Связи ObjectId не являются автоматически контролируемыми внешними ключами. Первичные cases имеют validationAction=warn; предметные коллекции — strict/error. Исходные спорные типы (например regex в chronic_diseases) не были произвольно изменены: для этого нужна отдельная предметная миграция.

## Роли и ограничения

| Роль/аккаунт | Права |
|---|---|
| admin.storage_admin / root | Полный административный доступ |
| admin.gis_admin | Назначаемая роль с наследованием root |
| Schema.app_user / gis_user | Технические find/insert/update модели, чтение cases; владельца проверяет backend |
| Schema.guest / gis_guest | Только чтение, кроме Social_group, Street, Building, Placement |
| etl_ingest | Чтение и добавление cases |
| etl_processor | Чтение cases и изменение модели |
| analyst | Внутренний читатель всей Schema; не Guest |

Repository добавляет `_owner_id` к чтению и атомарному обновлению, назначает его при создании и запрещает подменять владельца. Principal должен приходить от будущей проверенной серверной аутентификации. HTTP-вход ещё отсутствует. Служебные пароли нельзя выдавать пользователю: прямое подключение app_user обходит проверку владельца. Старым документам владелец автоматически не назначается.

Guest ограничен по коллекциям, а не по всем персональным полям. Cases.raw может содержать чувствительные сведения: обезличивание не реализовано. Исходные cases через Repository не редактируются. Плагин в будущем должен обращаться к backend API и не хранить MongoDB-пароли.

## Порты и ресурсы

Backend подключается к `storage:27017` в storage_net, будущий dashboard — к `backend:8000` в app_net. localhost внутри контейнера означает сам контейнер. MongoDB наружу по умолчанию не опубликована. Для аварийного доступа: `up --connections --emergency`; Compass подключается к 127.0.0.1:27017 с authSource=admin для root или Schema для служебного аккаунта.

Storage ограничен 4 GiB, двумя CPU и кэшем WiredTiger 1,5 GiB. Backend — 256 MiB и 0,5 CPU, пулы по четыре соединения плюс служебные соединения драйвера. Контейнерная память не равна общей памяти машины. Логи ротируются; данные находятся в именованных томах. Нет TTL, удаляющего первичные данные. Docker-образы закреплены по веткам, не digest; обновления следует предварительно проверять.

## Проверки и публикация на GitHub

```powershell
py scripts/manage.py test
py scripts/check_project.py
py scripts/manage.py integration
```

Первая команда не использует настоящую базу. Третья создаёт отдельные тома, проверяет RBAC, BSON, HTTP, повторный provision, миграцию старых имён, восстановление отсутствующего guest и сохранность после перезапуска, затем удаляет только тестовые тома. На рабочей базе миграция автоматически не выполняется.

Перед публикацией:

```bash
git init
git add .
git status --short
git diff --cached --stat
```

Проверьте список: .env, резервные копии и пользовательские медицинские данные не должны попасть в commit. Затем создайте commit и добавьте адрес своего GitHub-репозитория. Готовый workflow запустится на push/PR; до его реального выполнения нельзя заявлять, что Windows/macOS/Docker-тесты прошли. Лицензию распространения должен выбрать владелец проекта; она не назначена автоматически. В этой задаче репозиторий на GitHub не создавался и не публиковался.

## Типовые ошибки

- `Start directory is not importable`: распакуйте весь проект, включая tests/__init__.py; запускайте manage.py, а не отдельный скопированный фрагмент.
- `FAIL ... role: ...`: обновите файлы целиком, выполните provision и verify. Ошибка указывает конкретную роль, а не предположительный неправильный пароль.
- `FAIL ... authentication/read: ...`: проверьте сохранённый пароль указанного пользователя. Provision не вращает существующие пароли.
- `keys/canonical is not defined`: признак смешанных старых фрагментов; замените весь комплект scripts/init, не дописывайте блок в конец verify.js.
- `External volume not found`: сверить имя старого тома; не создавать пустую замену при обновлении.
- Healthy у Storage и 503 у backend: проверка процесса успешна, но служебное подключение не прошло. Выполните verify.
- 501 на /v1/*: ожидаемый ответ заготовки бизнес-API.

Источники технических решений: [MongoDB getRole](https://www.mongodb.com/docs/v8.0/reference/method/db.getrole/), [Python unittest discovery](https://docs.python.org/3/library/unittest.html#test-discovery), [Docker Compose networking](https://docs.docker.com/compose/how-tos/networking/).

## Изменения из чата диагностики: сети и MongoDB Compass

app_net использует bridge/internal:false; storage_net — bridge/internal:true. Для применения изменения уже существующих сетей выполните из корня проекта:

```powershell
docker compose -p gis-mongodb --profile connections down
py scripts/manage.py up --connections --local-api
```

Команда down приведена без -v: тома с данными сохраняются. Проверка сетей:

```powershell
docker network inspect gis-mongodb_app_net --format '{{.Internal}}'
docker network inspect gis-mongodb_storage_net --format '{{.Internal}}'
```

Ожидаются false и true соответственно. Проверка backend:

```powershell
curl.exe -i http://127.0.0.1:8000/health/live
```

Для Compass используйте отдельный overlay из диагностического чата:

```powershell
docker compose -p gis-mongodb -f docker-compose.yml -f docker-compose.local.yml -f docker-compose.compass.yml --profile connections up -d --no-deps --force-recreate storage
```

Storage подключается к storage_net и app_net, порт публикуется только на 127.0.0.1:27018. В MongoDB Compass задайте host 127.0.0.1, port 27018, username storage_admin, пароль из MONGO_ROOT_PASSWORD в существующем .env, authentication database admin. Вариант URI:

```text
mongodb://storage_admin:<PASSWORD>@127.0.0.1:27018/?authSource=admin&directConnection=true
```

В Linux/macOS вместо py используйте python3, а вместо curl.exe — curl. Отдельного параметра Compass в manage.py нет: применяется приведённая команда Compose. Повторный up через manage.py без этого overlay вернёт обычную конфигурацию Storage; для подключения Compass снова примените overlay.
