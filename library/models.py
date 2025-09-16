from django.db import models


class Author(models.Model):
    """Автор книги."""

    full_name = models.CharField(max_length=255, db_index=True)
    birth_date = models.DateField(null=True, blank=True)

    def __str__(self) -> str:
        return self.full_name


class Book(models.Model):
    """Книга (связана с автором)."""

    title = models.CharField(max_length=255, db_index=True)
    year = models.IntegerField(db_index=True)
    author = models.ForeignKey(
        Author,
        on_delete=models.CASCADE,
        related_name="books",
    )

    class Meta:
        indexes = [
            models.Index(fields=["author", "year"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.year})"


class Library(models.Model):
    """Библиотека с ограниченной вместимостью."""

    name = models.CharField(max_length=255, unique=True)
    capacity = models.PositiveIntegerField(
        help_text="Максимум экземпляров (всех книг)",
    )

    def __str__(self) -> str:
        return self.name

    @property
    def used_capacity(self) -> int:
        """Фактически занятое количество экземпляров книг в библиотеке."""
        return sum(self.holdings.values_list("quantity",  # type: ignore
                                             flat=True))


class LibraryBook(models.Model):
    """Связь книги и библиотеки с указанием количества экземпляров."""

    library = models.ForeignKey(
        Library,
        on_delete=models.CASCADE,
        related_name="holdings",
    )
    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name="placements",
    )
    quantity = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["library", "book"],
                name="uniq_library_book",
            ),
            models.CheckConstraint(
                check=models.Q(quantity__gte=0),
                name="quantity_non_negative",
            ),
        ]
        indexes = [
            models.Index(fields=["book", "library"]),
            models.Index(fields=["library", "book"]),
        ]

    def __str__(self) -> str:
        return f"{self.library} — {self.book}: {self.quantity} шт"
