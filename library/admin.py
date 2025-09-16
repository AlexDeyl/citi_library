from django.contrib import admin
from .models import Author, Book, Library, LibraryBook


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    search_fields = ('full_name',)


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'year', 'author')
    list_filter = ('year', 'author')
    search_fields = ('title',)


@admin.register(Library)
class LibraryAdmin(admin.ModelAdmin):
    list_display = ('name', 'capacity')
    search_fields = ('name',)


@admin.register(LibraryBook)
class LibraryBookAdmin(admin.ModelAdmin):
    list_display = ('library', 'book', 'quantity')
    list_filter = ('library', 'book__author')
    search_fields = ('book__title', 'library__name')
