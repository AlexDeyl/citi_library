from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from django.db import transaction
from django.db.models import F, Q, Count, Sum

from library.models import Book, Library, LibraryBook


@dataclass
class Move:
    """Описывает одно перемещение книги из одной библиотеки в другую."""

    book_id: int
    from_library_id: int
    to_library_id: int
    quantity: int = 1  # двигаем по 1 для равномерного покрытия


@dataclass
class Plan:
    """Результат работы перераспределения."""

    moves: List[Move]
    total_moves: int
    books_considered: int


class RedistributionManager:
    """
    Базовый менеджер перераспределения.

    Стремится, чтобы каждая библиотека имела >=1 экземпляр книги,
    если суммарный тираж позволяет. Вместимость библиотек НЕ учитывается.
    """

    def __init__(self, dry_run: bool = True) -> None:
        """Создать менеджер (dry_run=True для симуляции без записи)."""
        self.dry_run = dry_run

    def _candidate_book_ids(self, nlibs: int) -> Iterable[int]:
        """
        Получить id книг, у которых покрытие < nlibs
        и есть хотя бы 1 экземпляр.

        Args:
            nlibs: количество библиотек в системе.
        """
        qs = (
            LibraryBook.objects.values("book_id")
            .annotate(
                covered=Count("library", filter=Q(quantity__gt=0)),
                total=Sum("quantity"),
            )
            .filter(covered__lt=nlibs, total__gt=0)
            .values_list("book_id", flat=True)
        )
        return qs.iterator(chunk_size=10_000)

    def _build_plan_for_book(self, book_id: int, nlibs: int) -> List[Move]:
        """
        Составить план перемещений для одной книги.

        Args:
            book_id: id книги.
            nlibs: количество библиотек.
        """
        holdings = list(
            LibraryBook.objects.filter(book_id=book_id).values(
                "library_id", "quantity"
            )
        )
        total = sum(h["quantity"] for h in holdings)
        if total == 0:
            return []

        target_coverage = min(nlibs, total)
        has_set = {h["library_id"] for h in holdings if h["quantity"] > 0}
        covered = len(has_set)
        if covered >= target_coverage:
            return []

        donors = sorted(
            [h for h in holdings if h["quantity"] > 1],
            key=lambda x: -x["quantity"],
        )
        all_lib_ids = set(Library.objects.values_list("id", flat=True))
        recipients = [lid for lid in (all_lib_ids - has_set)]

        moves: List[Move] = []
        ri = 0
        for donor in donors:
            can_move = donor["quantity"] - 1  # минимум 1 оставляем
            while (
                can_move > 0
                and covered < target_coverage
                and ri < len(recipients)
            ):
                to_lib = recipients[ri]
                moves.append(
                    Move(
                        book_id=book_id,
                        from_library_id=donor["library_id"],
                        to_library_id=to_lib,
                        quantity=1,
                    )
                )
                ri += 1
                can_move -= 1
                covered += 1
            if covered >= target_coverage:
                break

        return moves

    def rebalance(self) -> Plan:
        """
        Выполнить перераспределение (dry-run или apply).

        Returns:
            Plan: план перемещений.
        """
        nlibs = Library.objects.count()
        moves: List[Move] = []
        considered = 0

        for book_id in self._candidate_book_ids(nlibs):
            considered += 1
            moves.extend(self._build_plan_for_book(book_id, nlibs))

        if not self.dry_run:
            self._apply_plan(moves)
        return Plan(
            moves=moves,
            total_moves=len(moves),
            books_considered=considered,
        )

    @transaction.atomic
    def _apply_plan(self, moves: List[Move]) -> None:
        """
        Применить перемещения к БД.

        Args:
            moves: список перемещений.
        """
        inc: Dict[Tuple[int, int], int] = {}
        dec: Dict[Tuple[int, int], int] = {}

        for m in moves:
            inc[(m.to_library_id, m.book_id)] = inc.get(
                (m.to_library_id, m.book_id), 0
            ) + m.quantity
            dec[(m.from_library_id, m.book_id)] = dec.get(
                (m.from_library_id, m.book_id), 0
            ) + m.quantity

        touched = set(list(inc.keys()) + list(dec.keys()))
        rows = (
            LibraryBook.objects.select_for_update()
            .filter(
                Q(library_id__in=[t[0] for t in touched])
                & Q(book_id__in=[t[1] for t in touched])
            )
        )
        by_key = {(r.library_id, r.book_id): r for r in rows}  # type: ignore

        to_create: List[LibraryBook] = []
        for (lib_id, book_id), qty in inc.items():
            row = by_key.get((lib_id, book_id))
            if row:
                row.quantity = F("quantity") + qty
                row.save(update_fields=["quantity"])
            else:
                to_create.append(
                    LibraryBook(
                        library_id=lib_id,
                        book_id=book_id,
                        quantity=qty,
                    )
                )
        if to_create:
            LibraryBook.objects.bulk_create(
                to_create, ignore_conflicts=True
            )

        for (lib_id, book_id), qty in dec.items():
            LibraryBook.objects.filter(
                library_id=lib_id, book_id=book_id
            ).update(quantity=F("quantity") - qty)


class CapacityAwareRedistributionManager(RedistributionManager):
    """
    Менеджер с учётом вместимости: не перемещаем, если нет свободного места.
    """

    def __init__(self, dry_run: bool = True) -> None:
        super().__init__(dry_run=dry_run)
        self._free_capacity: Dict[int, int] = {}

    def _compute_free_capacity(self) -> None:
        """Вычислить свободную вместимость для всех библиотек."""
        qs = (
            Library.objects.values("id", "capacity")
            .annotate(used=Sum("holdings__quantity"))
        )
        self._free_capacity = {
            row["id"]: int(row["capacity"] - (row["used"] or 0))
            for row in qs
        }

    def _build_plan_for_book(self, book_id: int, nlibs: int) -> List[Move]:
        """Построить план для книги с учётом вместимости библиотек."""
        if not self._free_capacity:
            self._compute_free_capacity()

        holdings = list(
            LibraryBook.objects.filter(book_id=book_id).values(
                "library_id", "quantity"
            )
        )
        total = sum(h["quantity"] for h in holdings)
        if total == 0:
            return []

        target_coverage = min(nlibs, total)
        has_set = {h["library_id"] for h in holdings if h["quantity"] > 0}
        covered = len(has_set)
        if covered >= target_coverage:
            return []

        donors = sorted(
            [h for h in holdings if h["quantity"] > 1],
            key=lambda x: -x["quantity"],
        )
        all_lib_ids = set(self._free_capacity.keys())
        recipients_all = [lid for lid in (all_lib_ids - has_set)]
        recipients = [
            lid for lid in recipients_all if self._free_capacity.get(lid,
                                                                     0) > 0
        ]

        moves: List[Move] = []
        ri = 0
        for donor in donors:
            can_move = donor["quantity"] - 1
            while (
                can_move > 0
                and covered < target_coverage
                and ri < len(recipients)
            ):
                to_lib = recipients[ri]
                if self._free_capacity[to_lib] <= 0:
                    ri += 1
                    continue
                moves.append(
                    Move(
                        book_id=book_id,
                        from_library_id=donor["library_id"],
                        to_library_id=to_lib,
                        quantity=1,
                    )
                )
                self._free_capacity[to_lib] -= 1
                ri += 1
                can_move -= 1
                covered += 1
            if covered >= target_coverage:
                break

        return moves


class PriorityRedistributionManager(CapacityAwareRedistributionManager):
    """
    Менеджер с приоритетами.

    Примеры:
      - 'year_desc' — новые книги первыми,
      - 'author_first' — книги указанных авторов первыми.
    """

    def __init__(
        self,
        dry_run: bool = True,
        *,
        priority: Optional[str] = None,
        author_ids: Optional[List[int]] = None,
    ) -> None:
        """Создать менеджер с приоритетной стратегией распределения."""
        super().__init__(dry_run=dry_run)
        self.priority = priority or "year_desc"
        self.author_ids = set(author_ids or [])

    def rebalance(self) -> Plan:
        """Перераспределить книги с учётом приоритета."""
        nlibs = Library.objects.count()
        considered = 0
        moves: List[Move] = []

        base_ids = list(self._candidate_book_ids(nlibs))
        book_meta = {
            b["id"]: b
            for b in Book.objects.filter(id__in=base_ids).values(
                "id", "year", "author_id"
            )
        }

        def sort_key(bid: int) -> Tuple[int, int]:
            meta = book_meta[bid]
            if self.priority == "author_first" and (
                meta["author_id"] in self.author_ids
            ):
                return (0, -meta["year"])
            if self.priority == "year_desc":
                return (1, -meta["year"])
            return (2, meta["id"])

        ordered = sorted(base_ids, key=sort_key)

        for book_id in ordered:
            considered += 1
            moves.extend(self._build_plan_for_book(book_id, nlibs))

        if not self.dry_run:
            self._apply_plan(moves)
        return Plan(
            moves=moves,
            total_moves=len(moves),
            books_considered=considered,
        )
