## Excel и работающий дашборд

[Полная инструкция: импорт Excel, порт 8501, проверка и ограничения данных](docs/EXCEL_DASHBOARD.md).

После `python3 scripts/manage.py up --connections --local-api` откройте http://127.0.0.1:8501.

# GIS-MongoDB — чистая установка

Хранилище MongoDB, backend и плагин QGIS для загрузки, создания и изменения точек Geodata. Архив содержит исходный код без .env, истории .git, рабочих данных и кэшей. Нужны Docker с Compose v2 в режиме Linux containers и Python 3.10+. На Windows/macOS запустите Docker Desktop. Node.js 22+ нужен только для локальных тестов.

## Запуск после клонирования или распаковки

Откройте терминал в папке с docker-compose.yml. Windows PowerShell:

```powershell
py scripts/manage.py init
py scripts/manage.py up --connections --local-api
```

Linux/macOS:

```bash
python3 scripts/manage.py init
python3 scripts/manage.py up --connections --local-api
```

init создаёт собственный .env с двумя API-токенами QGIS, шестью случайными паролями и уникальными именами томов. Compose сам создаёт тома. На пустой базе скрипты создают коллекции, роли и пользователей. Никаких заранее существующих учётных записей или томов не требуется. Имена ролей в коде — определения прав, а не чужие учётные данные.

Ожидайте Healthy у Storage и backend. Откройте http://127.0.0.1:8000/health/ready . Это диагностический JSON. Плагин устанавливается из dist/qgis_mongodb.zip по инструкции docs/QGIS.md.

При следующих запусках выполняйте только up. Сохраняйте созданный .env: повторная генерация конфигурации создаёт другие имена томов и пароли. Для остановки используйте `py scripts/manage.py stop`. Данные останутся в томах. Не используйте down -v для обычной остановки.

## Подключение QGIS

После запуска установите модуль из `dist/qgis_mongodb.zip` через менеджер модулей QGIS. Введите адрес backend и QGIS_GUEST_TOKEN для просмотра либо QGIS_USER_TOKEN для собственных редактируемых точек. Для существующего .env сначала выполните `py scripts/manage.py configure`, затем повторный up.

[Пошаговая инструкция QGIS](docs/QGIS.md)

## Проверки

```powershell
py scripts/manage.py verify
py scripts/manage.py network-test
py scripts/manage.py test
py scripts/check_project.py
```

Для настоящих Docker-тестов на отдельных временных томах: `py scripts/manage.py integration`. При ограниченной памяти сначала остановите основной стек. В Linux/macOS замените py на python3.

## MongoDB Compass

```powershell
docker compose -p gis-mongodb -f docker-compose.yml -f docker-compose.local.yml -f docker-compose.compass.yml --profile connections up -d --no-deps --force-recreate storage
```

Подключение: 127.0.0.1:27018; пользователь storage_admin; пароль из вашего MONGO_ROOT_PASSWORD; authentication database admin. Обычный up без overlay отключает этот дополнительный доступ.

## Публикация

Поставка подготовлена без старой истории Git и адресов origin. Для нового пустого репозитория:

```bash
git init -b main
git add .
git status --short
git commit -m "Prepare clean installation"
git remote add origin <URL-ВАШЕГО-РЕПОЗИТОРИЯ>
git push -u origin main
```

Для существующего клона скопируйте исходники из этой поставки, сохранив его .git; проверьте git diff, затем commit и push. Повторно добавлять origin не нужно. Не переносите старый .env или данные в Git. Если .env уже был опубликован, удаление из новой поставки не удаляет его из истории: замените раскрытые пароли.

GitHub Actions выполняет локальные тесты на Windows/Linux/macOS и интеграцию Docker на Ubuntu. Фактический статус проверки смотрите в Actions после push. В этой поставке публикация не выполнялась.

[Учебная инструкция](docs/STUDENT_GUIDE.md) · [Техническая справка](docs/REFERENCE.md) · [Проверки](tests/VERIFICATION.md)

Для обновления предыдущей версии с QGIS сохраните существующую .env и следуйте docs/EXCEL_DASHBOARD.md. Для старых редакций со старой схемой см. docs/UPGRADE.md; миграции при чистом запуске не нужны.
