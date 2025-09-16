import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from library.models import Author, Book, Library, LibraryBook


class Command(BaseCommand):
    """Загружает авторов/книги/библиотеки из JSON."""

    help = (
        "Загружает авторов/книги/библиотеки из JSON и (по желанию) "
        "создаёт стартовые остатки."
    )

    def add_arguments(self, parser) -> None:
        """Описать CLI-аргументы команды."""
        parser.add_argument(
            "json_path",
            type=str,
            help="Путь до файла JSON с данными",
        )
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Очистить таблицы перед загрузкой",
        )
        parser.add_argument(
            "--seed-holdings",
            choices=["none", "all_to_first", "random"],
            default="none",
            help=(
                "Сценарий начальных остатков: "
                "все в первую библиотеку или случайно (демо)"
            ),
        )
        parser.add_argument(
            "--random-copies",
            type=int,
            default=2,
            help="Макс. доп. экз. при random (кроме 1 базового)",
        )

    def handle(self, *args, **opts) -> None:
        """Выполнить загрузку JSON и опционально сгенерировать остатки."""
        path = Path(opts["json_path"])
        if not path.exists():
            raise CommandError(f"Файл не найден: {path}")

        data = json.loads(path.read_text(encoding="utf-8"))

        # Загружаем справочники атомарно
        with transaction.atomic():
            if opts["flush"]:
                LibraryBook.objects.all().delete()
                Book.objects.all().delete()
                Author.objects.all().delete()
                Library.objects.all().delete()

            authors = [
                Author(
                    id=a["id"],
                    full_name=a["full_name"],
                    birth_date=a["birth_date"],
                )
                for a in data["authors"]
            ]
            Author.objects.bulk_create(authors, ignore_conflicts=True)

            books = [
                Book(
                    id=b["id"],
                    title=b["title"],
                    year=b["year"],
                    author_id=b["author_id"],
                )
                for b in data["books"]
            ]
            Book.objects.bulk_create(books, ignore_conflicts=True)

            libs = [
                Library(
                    id=li["id"],
                    name=li["name"],
                    capacity=li["capacity"],
                )
                for li in data["libraries"]
            ]
            Library.objects.bulk_create(libs, ignore_conflicts=True)

        # Генерация начальных остатков (по желанию)
        scenario = opts["seed_holdings"]
        if scenario == "none":
            self.stdout.write(
                self.style.WARNING(
                    "Остатки не сгенерированы (seed-holdings=none)."
                )
            )
            return

        if scenario == "all_to_first":
            first_lib = Library.objects.order_by("id").first()
            if not first_lib:
                raise CommandError(
                    "Нет библиотек для сценария all_to_first"
                )
            to_create = [
                LibraryBook(library=first_lib,
                            book_id=b.id, quantity=1)  # type: ignore
                for b in Book.objects.all()
            ]
            LibraryBook.objects.bulk_create(
                to_create, ignore_conflicts=True
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Созданы остатки: по 1 экз. каждой книги "
                    f"в «{first_lib.name}»."
                )
            )

        elif scenario == "random":
            import random  # noqa: WPS433 — локальный импорт осознанно

            libs = list(Library.objects.all())
            to_create = []
            for b in Book.objects.all().iterator():
                base_lib = random.choice(libs)
                to_create.append(
                    LibraryBook(
                        library=base_lib,
                        book_id=b.id,  # type: ignore
                        quantity=1,
                    )
                )
                extra = random.randint(0, opts["random_copies"])
                others = random.sample(libs, k=min(extra, len(libs)))
                for lib in others:
                    if lib == base_lib:
                        continue
                    to_create.append(
                        LibraryBook(
                            library=lib,
                            book_id=b.id,  # type: ignore
                            quantity=1,
                        )
                    )
            LibraryBook.objects.bulk_create(
                to_create, ignore_conflicts=True
            )
            self.stdout.write(
                self.style.SUCCESS("Случайные остатки сгенерированы.")
            )
