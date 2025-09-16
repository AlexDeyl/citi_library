# City Library — система перераспределения книг

Тестовый проект на Django: выравнивает распределение книг между библиотеками с учётом вместимости.  
Поддерживает dry-run план и применение изменений, быстро грузит сид-данные и умеет симулировать «приём книг» в одну библиотеку.

## Стек
- Python 3.13+ (подойдёт и 3.10)
- Django 5.2.x
- SQLite (для простого локального развёртывания)
- `python-dotenv` для читаемого `.env`

---

## Быстрый старт (локально)

```bash
# 0) Клонируем репозиторий
git clone <URL-ВАШЕГО-РЕПО> && cd <папка проекта>

# 1) Виртуальное окружение
python -m venv .venv
# Win: .venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate

# 2) Устанавливаем зависимости
pip install -r requirements.txt
# Для разработки (линтеры/тесты):
# pip install -r requirements-dev.txt

# 3) Настраиваем секреты
cp .env.example .env
# Откройте .env и задайте DJANGO_SECRET_KEY (можно сгенерировать командой ниже)
python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"

# 4) Миграции
python manage.py migrate

# 5) (Опционально) Суперпользователь для админки
python manage.py createsuperuser

# 6) Запуск
python manage.py runserver
# http://127.0.0.1:8000/ (админка: /admin)
