from django.core.management.base import BaseCommand

from library.models import Book
from library.services.redistribution import (
    CapacityAwareRedistributionManager,
    PriorityRedistributionManager,
    RedistributionManager,
)


class Command(BaseCommand):
    help = (
        "Вычисляет и (опционально) применяет план перераспределения книг "
        "между библиотеками."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Применить изменения (по умолчанию dry-run)",
        )
        parser.add_argument(
            "--capacity-aware",
            action="store_true",
            help="Учитывать вместимость библиотек",
        )
        parser.add_argument(
            "--priority",
            choices=["year_desc", "author_first"],
            default="year_desc",
            help=(
                "Стратегия приоритета "
                "(для PriorityRedistributionManager)"
            ),
        )
        parser.add_argument(
            "--authors",
            type=str,
            default="",
            help="Список author_id через запятую для author_first",
        )

    def handle(self, *args, **opts):
        dry_run = not opts["apply"]
        authors = [
            int(x)
            for x in opts["authors"].split(",")
            if x.strip().isdigit()
        ]

        if opts["capacity_aware"] and (opts["priority"] or authors):
            mgr = PriorityRedistributionManager(
                dry_run=dry_run,
                priority=opts["priority"],
                author_ids=authors,
            )
        elif opts["capacity_aware"]:
            mgr = CapacityAwareRedistributionManager(dry_run=dry_run)
        else:
            mgr = RedistributionManager(dry_run=dry_run)

        plan = mgr.rebalance()

        self.stdout.write(
            "\n" + self.style.MIGRATE_HEADING("План перераспределения")
        )
        self.stdout.write(f"Рассмотрено книг: {plan.books_considered}")
        self.stdout.write(f"Предложено перемещений: {plan.total_moves}\n")

        if plan.total_moves == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    "Все книги уже распределены максимально равномерно, "
                    "дополнительных перемещений не требуется."
                )
            )
        else:
            for i, m in enumerate(plan.moves[:50], start=1):
                book = Book.objects.only("title").get(id=m.book_id)
                self.stdout.write(
                    f"{i:>3}. '{book.title}': "
                    f"{m.from_library_id} -> {m.to_library_id} "
                    f"(x{m.quantity})"
                )
            if plan.total_moves > 50:
                rest = plan.total_moves - 50
                self.stdout.write(f"... и ещё {rest} перемещений")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "\nDRY-RUN: изменения НЕ применены. "
                    "Запустите с --apply для записи."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("\nИзменения применены."))
