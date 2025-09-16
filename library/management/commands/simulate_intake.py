import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F

from library.models import Book, Library, LibraryBook


class Command(BaseCommand):
    """
    Симулирует приём книг в одну библиотеку.

    Добавляет +copies экземпляров указанным книгам (или случайным)
    в выбранной библиотеке.
    """

    help = (
        "Симулирует приём книг в одну библиотеку: добавляет"
        "+copies экземпляров "
        "указанным книгам (или случайным) в выбранной библиотеке."
    )

    def add_arguments(self, parser) -> None:
        """Описать CLI-аргументы команды."""
        parser.add_argument(
            "--library-id",
            type=int,
            default=None,
            help=(
                "ID библиотеки, куда «принесли» книги "
                "(по умолчанию — первая по id)"
            ),
        )
        parser.add_argument(
            "--book-ids",
            type=str,
            default="",
            help=(
                "Список id книг через запятую "
                "(если не задано — выберем случайные)"
            ),
        )
        parser.add_argument(
            "--random-count",
            type=int,
            default=10,
            help="Сколько случайных книг выбрать, если book-ids не передан",
        )
        parser.add_argument(
            "--copies",
            type=int,
            default=1,
            help="Сколько экземпляров добавить каждой выбранной книге",
        )

    @transaction.atomic
    def handle(self, *args, **opts) -> None:
        """Выполнить симуляцию приёма книг."""
        # 1. Определяем целевую библиотеку
        library_id = opts["library_id"]
        lib = (
            Library.objects.filter(id=library_id).first()
            if library_id
            else Library.objects.order_by("id").first()
        )
        if not lib:
            raise CommandError("Не найдена целевая библиотека.")

        # 2. Определяем список книг
        raw_ids = [
            s for s in opts["book_ids"].split(",") if s.strip().isdigit()
        ]
        if raw_ids:
            book_ids = list(map(int, raw_ids))
        else:
            all_ids = list(Book.objects.values_list("id", flat=True))
            if not all_ids:
                raise CommandError("В системе нет книг.")
            k = min(int(opts["random_count"]), len(all_ids))
            book_ids = random.sample(all_ids, k=k)

        # 3. Количество копий
        copies = max(1, int(opts["copies"]))

        # 4. Обеспечиваем наличие строк LibraryBook
        existing = {
            lb.book_id: lb  # type: ignore
            for lb in LibraryBook.objects.filter(
                library=lib, book_id__in=book_ids
            )
        }
        to_create = [
            LibraryBook(library=lib, book_id=bid, quantity=0)
            for bid in book_ids
            if bid not in existing
        ]
        if to_create:
            LibraryBook.objects.bulk_create(to_create, ignore_conflicts=True)

        # 5. Обновляем количество
        updated = (
            LibraryBook.objects.filter(library=lib, book_id__in=book_ids)
            .update(quantity=F("quantity") + copies)
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"В «{lib.name}» добавлено +{copies} экз. "
                f"для {len(book_ids)} книг (обновлено строк: {updated})."
            )
        )
