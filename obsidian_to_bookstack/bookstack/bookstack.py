import os
import shutil
from datetime import datetime, timedelta
from typing import List

import urllib3

from ..console import console
from ..utils import con_hash
from .artifacts import Book, Chapter, Page, Shelf
from .client import LocalClient, RemoteClient
from .collectors.local import *
from .collectors.remote import *
from .constants import *


class BookstackClient(RemoteClient):
    """Represents the remote Bookstack instance"""

    def __init__(self, verbose: bool) -> None:
        # if verbose is set, will issue logs
        super().__init__()
        self.verbose = verbose
        if self.verbose:
            console.log("Building remote client...")

        self.__set_collectors()
        self.__set_artifacts()
        self.__set_maps()

    def __set_collectors(self):
        self.shelf_collector = RemoteShelfCollector(self.verbose, self)
        self.book_collector = RemoteBookCollector(self.verbose, self)
        self.page_collector = RemotePageCollector(self.verbose, self)
        self.chapter_collector = RemoteChapterCollector(self.verbose, self)

    def __set_artifacts(self):
        self.shelves: List[Shelf] = self.shelf_collector.get_shelves()
        self.books: List[Book] = self.book_collector.get_books(self.shelves)
        self.pages: List[Page] = self.page_collector.get_pages(self.books)
        self.chapters: List[Chapter] = self.chapter_collector.get_chapters(self.books)

    def __set_maps(self):
        self.shelf_map = self._build_shelf_map()
        self.book_map = self._build_book_map()
        self.page_map = self._build_page_map()
        self.chapter_map = self._build_chapter_map()

    def _refresh(self):
        """Simply update the client"""
        self.http = urllib3.PoolManager()
        self.__set_collectors()
        self.__set_artifacts()
        self.__set_maps()

    def _build_shelf_map(self):
        """Build a map of all client shelves"""
        return {con_hash(shelf.name): shelf for shelf in self.shelves}

    def _build_book_map(self):
        """Build a map of all client books"""
        book_map = {}
        for book in self.books:
            if book.shelf:
                book_map[con_hash(book.name + book.shelf.name)] = book
            else:
                book_map[con_hash(book.name)] = book

        return book_map

    def _build_page_map(self):
        """Build a map of all client pages"""
        page_map = {}
        for page in self.pages:
            if page.chapter and page.book:
                page_map[
                    con_hash(page.name + page.book.name + page.chapter.name)
                ] = page

            elif page.book:
                page_map[con_hash(page.name + page.book.name)] = page

            else:
                page_map[con_hash(page.name)] = page

        return page_map

    def _build_chapter_map(self):
        """Build a map of all client chapters"""
        page_map = {}
        for chapter in self.chapters:
            if chapter.book:
                page_map[con_hash(chapter.name + chapter.book.name)] = chapter

        return page_map

    def _get_temp_book_map(self):
        """Get books from the client, but don't add to the client"""
        books = self._get_from_client(BookstackAPIEndpoints.BOOKS)
        return {book["name"]: book["id"] for book in books}

    def _retrieve_from_client_map(self, obj: Page | Shelf | Book | Chapter):
        """Retrieve the client version of the local object"""
        if isinstance(obj, Page):
            name = os.path.splitext(obj.name)[0]

            if obj.chapter and obj.book:
                return self.page_map[con_hash(name + obj.book.name + obj.chapter.name)]

            return (
                self.page_map[con_hash(name + obj.book.name)]
                if obj.book
                else self.page_map[con_hash(name)]
            )

        if isinstance(obj, Book):
            return (
                self.book_map[con_hash(obj.name + obj.shelf.name)]
                if obj.shelf
                else self.book_map[con_hash(obj.name)]
            )

        if isinstance(obj, Shelf):
            return self.shelf_map[con_hash(obj.name)]

        if isinstance(obj, Chapter):
            return self.chapter_map[con_hash(obj.name + obj.book.name)]


class Bookstack(LocalClient):
    """Represents the local Bookstack notes instance"""

    def __init__(self, path, excluded, verbose: bool) -> None:
        self.verbose = verbose
        if self.verbose:
            console.log("Building local client...")

        self.client = BookstackClient(verbose=self.verbose)
        self.path = path
        self.excluded = excluded
        self.__set_collectors()
        self.__set_artifacts()
        self.missing_books = set()

    def __set_collectors(self):
        self.shelf_collector = LocalShelfCollector(
            self, self.client, self.path, self.excluded, self.verbose
        )
        self.book_collector = LocalBookCollector(
            self, self.client, self.path, self.excluded, self.verbose
        )
        self.page_collector = LocalPageCollector(
            self, self.client, self.path, self.excluded, self.verbose
        )
        self.chapter_collector = LocalChapterCollector(
            self, self.client, self.path, self.excluded, self.verbose
        )

    def __set_artifacts(self):
        self.shelves = self.shelf_collector.set_shelves()
        self.books = self.book_collector.set_books(self.shelves)
        self.chapters = self.chapter_collector.set_chapters(self.books)
        self.pages = self.page_collector.set_pages(self.books)

    def _refresh(self):
        # refresh objects
        if self.verbose:
            console.log("Refreshing local client")

        self.__set_artifacts()

    def _build_object_for_delete(self, item_type: BookstackItems, path_parts: list):
        """Builds the correct artifact object from path parts for deletion lookup."""
        if item_type == BookstackItems.SHELF:
            return Shelf(name=path_parts[0])
        elif item_type == BookstackItems.BOOK:
            shelf = Shelf(name=path_parts[0])
            return Book(name=path_parts[1], shelf=shelf)
        elif item_type == BookstackItems.CHAPTER:
            shelf = Shelf(name=path_parts[0])
            book = Book(name=path_parts[1], shelf=shelf)
            return Chapter(name=path_parts[2], book=book)
        elif item_type == BookstackItems.PAGE:
            shelf = Shelf(name=path_parts[0])
            book = Book(name=path_parts[1], shelf=shelf)
            # Handle pages in chapters vs. pages in books
            if len(path_parts) == 4:
                chapter = Chapter(name=path_parts[2], book=book)
                return Page(name=path_parts[3], book=book, chapter=chapter)
            else:
                return Page(name=path_parts[2], book=book)
        return None

    def delete(self, item_type: BookstackItems, item_path_str: str):
        """Delete item from both local Obsidian Vault and remote Bookstack instance"""
        path_parts = item_path_str.split(os.path.sep)

        # 1. Delete local file/directory
        local_path = os.path.join(self.path, *path_parts)
        if item_type == BookstackItems.PAGE:
            # Append .md for pages and remove file
            local_path += ".md"
            if os.path.exists(local_path):
                if self.verbose:
                    console.log(f"Deleting local file: {local_path}")
                os.remove(local_path)
        else:
            # Remove directory for shelves, books, chapters
            if os.path.isdir(local_path):
                if self.verbose:
                    console.log(f"Deleting local directory: {local_path}")
                shutil.rmtree(local_path)

        # 2. Build a temporary object to find the remote equivalent
        lookup_obj = self._build_object_for_delete(item_type, path_parts)
        if not lookup_obj:
            console.log(f"[bold red]Error:[/bold red] Could not build object for path '{item_path_str}'")
            return

        try:
            client_obj = self.client._retrieve_from_client_map(lookup_obj)
        except KeyError:
            console.log(
                f"[bold yellow]Warning:[/bold yellow] Could not find remote equivalent for '{item_path_str}'. It may have already been deleted."
            )
            return

        # 3. Construct the correct API endpoint and delete the remote object
        endpoint_map = {
            BookstackItems.SHELF: BookstackAPIEndpoints.SHELVES,
            BookstackItems.BOOK: BookstackAPIEndpoints.BOOKS,
            BookstackItems.CHAPTER: BookstackAPIEndpoints.CHAPTERS,
            BookstackItems.PAGE: BookstackAPIEndpoints.PAGES,
        }

        endpoint = endpoint_map.get(item_type)
        if not endpoint:
            return

        class DeletionLink(DetailedBookstackLink):
            LINK = f"{endpoint.value}/{client_obj.details['id']}"

        if self.verbose:
            console.log(
                f"Deleting remote {item_type.value}: {client_obj} (id: {client_obj.details['id']})"
            )

        self._delete_from_bookstack(DeletionLink.LINK)

    def _delete_from_bookstack(self, link: DetailedBookstackLink):
        """Make a DELETE request to a Bookstack API link"""
        resp = self.client._make_request(RequestType.DELETE, link)
        return resp

    def sync_remote(self):
        """Sync local changes to the remote."""
        self.shelf_collector.create_remote_missing_shelves()
        self.missing_books = self.book_collector._create_remote_missing_books()
        self.client._refresh()  # refresh to update book and page ids
        self._refresh()
        self.book_collector.update_shelf_books(self.missing_books)
        self.client._refresh()  # refresh to update book and page ids
        self.chapter_collector.create_remote_missing_chapters()
        self.page_collector.create_remote_missing_pages()
        self.client._refresh()  # refresh to include newly created pages and chapters

    def sync_local(self):
        """Sync any remote changes to local store"""
        self.shelf_collector.create_local_missing_shelves()
        self.book_collector.create_local_missing_books()
        self.chapter_collector.create_local_missing_chapters()
        self.page_collector.create_local_missing_pages()

    def purge_local(self):
        """Deletes local files that do not exist on the remote."""
        if self.verbose:
            console.log("Purging local files not found on remote...")

        # The order is important: from most nested to least (pages -> chapters -> books -> shelves)

        # Purge pages
        extra_pages = self.page_collector._get_missing_set(
            BookstackItems.PAGE, SyncType.REMOTE
        )
        for page in extra_pages:
            if os.path.exists(page.path):
                if self.verbose:
                    console.log(f"Purging local page: {page.path}")
                os.remove(page.path)

        # Purge chapters
        extra_chapters = self.chapter_collector._get_missing_set(
            BookstackItems.CHAPTER, SyncType.REMOTE
        )
        for chapter in extra_chapters:
            if os.path.isdir(chapter.path):
                if self.verbose:
                    console.log(f"Purging local chapter: {chapter.path}")
                shutil.rmtree(chapter.path)

        # Purge books
        extra_books = self.book_collector._get_missing_set(
            BookstackItems.BOOK, SyncType.REMOTE
        )
        for book in extra_books:
            if os.path.isdir(book.path):
                if self.verbose:
                    console.log(f"Purging local book: {book.path}")
                shutil.rmtree(book.path)

        # Purge shelves
        extra_shelves = self.shelf_collector._get_missing_set(
            BookstackItems.SHELF, SyncType.REMOTE
        )
        for shelf in extra_shelves:
            if os.path.isdir(shelf.path):
                if self.verbose:
                    console.log(f"Purging local shelf: {shelf.path}")
                shutil.rmtree(shelf.path)

    def purge_remote(self):
        """Deletes remote items that do not exist locally."""
        if self.verbose:
            console.log("Purging remote items not found locally...")

        # The order is important: from most nested to least (pages -> chapters -> books -> shelves)

        for item_type in [
            BookstackItems.PAGE,
            BookstackItems.CHAPTER,
            BookstackItems.BOOK,
            BookstackItems.SHELF,
        ]:
            collector = getattr(self, f"{item_type.value}_collector")
            extra_items = collector._get_missing_set(item_type, SyncType.LOCAL)
            for item in extra_items:
                if self.verbose:
                    console.log(f"Purging remote {item_type.value}: {item.get_full_path_str()}")
                self.delete(item_type, item.get_full_path_str())

    def update_remote(self, remote: bool, local: bool):
        """Sync page contents to the remote"""
        updated_pages = []

        for page in self.pages:
            file_stat = os.stat(page.path)

            updated_at = datetime.utcfromtimestamp(file_stat.st_mtime)

            client_page = self.client._retrieve_from_client_map(page)

            client_updated = datetime.strptime(
                client_page.details["updated_at"], "%Y-%m-%dT%H:%M:%S.%fZ"
            )

            if remote:
                if updated_at > client_updated and (
                    updated_at - client_updated
                ) > timedelta(
                    seconds=5  # TODO: Surely there's a better way to tell the difference without downloading content
                ):
                    updated_pages.append(client_page)
                    self.page_collector.update_local_content(page, client_page)
            elif local:
                if updated_at < client_updated and (
                    client_updated - updated_at
                ) > timedelta(seconds=5):
                    console.log(f"Updating local page: {page}")
                    updated_pages.append(page)
                    content = self.page_collector.update(client_page)
                    with open(page.path, "wb") as f:
                        f.write(content)

        if not updated_pages and self.verbose:
            console.log("No pages changed to update")
