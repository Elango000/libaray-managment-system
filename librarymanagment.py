#!/usr/bin/env python3
"""
Library Management System (CLI, SQLite)
---------------------------------------
Single-file Python app for managing books, members, and loans.
- Creates `library.db` automatically on first run.
- Features: add/list/search books & members, borrow/return, overdue list, delete, basic reports.

Run:
  python library.py

Test data:
  Use menu option [9] to load a few sample books & members.

Author: ChatGPT
"""
from __future__ import annotations
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from typing import Optional, Iterable, Tuple
import os

DB_FILE = os.path.join(os.path.dirname(__file__), "library.db")
DATE_FMT = "%Y-%m-%d"

# ------------------------- DB SETUP -------------------------

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing(get_conn()) as conn, conn:
        conn.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                isbn TEXT UNIQUE,
                copies_total INTEGER NOT NULL DEFAULT 1,
                copies_available INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE,
                phone TEXT,
                joined_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS loans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
                loan_date TEXT NOT NULL,
                due_date TEXT NOT NULL,
                return_date TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_loans_book ON loans(book_id);
            CREATE INDEX IF NOT EXISTS idx_loans_member ON loans(member_id);
            """
        )


# ------------------------- HELPERS -------------------------


def today() -> str:
    return datetime.now().strftime(DATE_FMT)


def parse_date(s: str) -> datetime:
    return datetime.strptime(s, DATE_FMT)


def input_int(prompt: str, min_val: Optional[int] = None, max_val: Optional[int] = None) -> int:
    while True:
        try:
            val = int(input(prompt).strip())
            if (min_val is not None and val < min_val) or (max_val is not None and val > max_val):
                print(f"Enter a number between {min_val} and {max_val}.")
                continue
            return val
        except ValueError:
            print("Please enter a valid integer.")


def print_rows(rows: Iterable[sqlite3.Row], headers: Optional[Iterable[str]] = None) -> None:
    rows = list(rows)
    if not rows:
        print("(no results)")
        return
    if headers is None:
        headers = rows[0].keys()
    widths = [max(len(str(h)), *(len(str(r[h])) for r in rows)) for h in headers]
    def fmt_row(r: Iterable) -> str:
        return " | ".join(str(v).ljust(w) for v, w in zip(r, widths))
    print(fmt_row(headers))
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        print(fmt_row([row[h] for h in headers]))


# ------------------------- BOOKS -------------------------


def add_book(title: str, author: str, isbn: Optional[str], copies: int) -> int:
    with closing(get_conn()) as conn, conn:
        now = today()
        cur = conn.execute(
            "INSERT INTO books (title, author, isbn, copies_total, copies_available, created_at) VALUES (?,?,?,?,?,?)",
            (title.strip(), author.strip(), isbn.strip() if isbn else None, copies, copies, now),
        )
        return cur.lastrowid


def list_books(keyword: Optional[str] = None) -> Iterable[sqlite3.Row]:
    with closing(get_conn()) as conn:
        if keyword:
            kw = f"%{keyword.lower()}%"
            return conn.execute(
                "SELECT * FROM books WHERE lower(title) LIKE ? OR lower(author) LIKE ? OR lower(ifnull(isbn,'')) LIKE ? ORDER BY id",
                (kw, kw, kw),
            ).fetchall()
        return conn.execute("SELECT * FROM books ORDER BY id").fetchall()


def delete_book(book_id: int) -> None:
    with closing(get_conn()) as conn, conn:
        # Prevent delete if active loan exists
        active = conn.execute(
            "SELECT COUNT(*) c FROM loans WHERE book_id=? AND return_date IS NULL",
            (book_id,),
        ).fetchone()[0]
        if active:
            print("Cannot delete: active loans exist for this book.")
            return
        conn.execute("DELETE FROM books WHERE id=?", (book_id,))
        print("Book deleted (if it existed).")


# ------------------------- MEMBERS -------------------------


def add_member(name: str, email: Optional[str], phone: Optional[str]) -> int:
    with closing(get_conn()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO members (name, email, phone, joined_at) VALUES (?,?,?,?)",
            (name.strip(), email.strip() if email else None, phone.strip() if phone else None, today()),
        )
        return cur.lastrowid


def list_members(keyword: Optional[str] = None) -> Iterable[sqlite3.Row]:
    with closing(get_conn()) as conn:
        if keyword:
            kw = f"%{keyword.lower()}%"
            return conn.execute(
                "SELECT * FROM members WHERE lower(name) LIKE ? OR lower(ifnull(email,'')) LIKE ? OR lower(ifnull(phone,'')) LIKE ? ORDER BY id",
                (kw, kw, kw),
            ).fetchall()
        return conn.execute("SELECT * FROM members ORDER BY id").fetchall()


def delete_member(member_id: int) -> None:
    with closing(get_conn()) as conn, conn:
        # Prevent delete if active loan exists
        active = conn.execute(
            "SELECT COUNT(*) c FROM loans WHERE member_id=? AND return_date IS NULL",
            (member_id,),
        ).fetchone()[0]
        if active:
            print("Cannot delete: member has active loans.")
            return
        conn.execute("DELETE FROM members WHERE id=?", (member_id,))
        print("Member deleted (if it existed).")


# ------------------------- LOANS -------------------------


def borrow_book(book_id: int, member_id: int, days: int = 14) -> Optional[int]:
    with closing(get_conn()) as conn, conn:
        book = conn.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
        if not book:
            print("Book not found.")
            return None
        if book["copies_available"] <= 0:
            print("No available copies.")
            return None
        loan_date = today()
        due_date = (parse_date(loan_date) + timedelta(days=days)).strftime(DATE_FMT)
        cur = conn.execute(
            "INSERT INTO loans (book_id, member_id, loan_date, due_date) VALUES (?,?,?,?)",
            (book_id, member_id, loan_date, due_date),
        )
        conn.execute(
            "UPDATE books SET copies_available = copies_available - 1 WHERE id=?",
            (book_id,),
        )
        print(f"Loan created. Due on {due_date}.")
        return cur.lastrowid


def return_book(loan_id: int) -> None:
    with closing(get_conn()) as conn, conn:
        loan = conn.execute("SELECT * FROM loans WHERE id=?", (loan_id,)).fetchone()
        if not loan:
            print("Loan not found.")
            return
        if loan["return_date"] is not None:
            print("Already returned.")
            return
        conn.execute(
            "UPDATE loans SET return_date=? WHERE id=?",
            (today(), loan_id),
        )
        conn.execute(
            "UPDATE books SET copies_available = copies_available + 1 WHERE id=?",
            (loan["book_id"],),
        )
        # Late notice
        due = parse_date(loan["due_date"]).date()
        if datetime.now().date() > due:
            late_days = (datetime.now().date() - due).days
            print(f"Returned late by {late_days} day(s).")
        else:
            print("Returned on time. Thank you!")


def list_loans(active_only: bool = False) -> Iterable[sqlite3.Row]:
    with closing(get_conn()) as conn:
        if active_only:
            q = (
                "SELECT l.*, b.title AS book_title, m.name AS member_name "
                "FROM loans l JOIN books b ON b.id=l.book_id JOIN members m ON m.id=l.member_id "
                "WHERE l.return_date IS NULL ORDER BY l.due_date"
            )
        else:
            q = (
                "SELECT l.*, b.title AS book_title, m.name AS member_name "
                "FROM loans l JOIN books b ON b.id=l.book_id JOIN members m ON m.id=l.member_id "
                "ORDER BY CASE WHEN l.return_date IS NULL THEN 0 ELSE 1 END, l.due_date"
            )
        return conn.execute(q).fetchall()


def list_overdue() -> Iterable[sqlite3.Row]:
    with closing(get_conn()) as conn:
        today_str = today()
        return conn.execute(
            "SELECT l.*, b.title AS book_title, m.name AS member_name "
            "FROM loans l JOIN books b ON b.id=l.book_id JOIN members m ON m.id=l.member_id "
            "WHERE l.return_date IS NULL AND l.due_date < ? ORDER BY l.due_date",
            (today_str,),
        ).fetchall()


# ------------------------- REPORTS -------------------------


def stats() -> Tuple[int, int, int, int]:
    with closing(get_conn()) as conn:
        books = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        members = conn.execute("SELECT COUNT(*) FROM members").fetchone()[0]
        active_loans = conn.execute("SELECT COUNT(*) FROM loans WHERE return_date IS NULL").fetchone()[0]
        overdue = conn.execute(
            "SELECT COUNT(*) FROM loans WHERE return_date IS NULL AND due_date < ?",
            (today(),),
        ).fetchone()[0]
        return books, members, active_loans, overdue


# ------------------------- SAMPLE DATA -------------------------


def load_sample_data() -> None:
    if list_books() or list_members():
        print("Database already has data; skipping samples.")
        return
    b1 = add_book("Clean Code", "Robert C. Martin", "9780132350884", 3)
    b2 = add_book("Fluent Python", "Luciano Ramalho", "9781491946008", 2)
    b3 = add_book("Automate the Boring Stuff with Python", "Al Sweigart", "9781593275990", 4)
    m1 = add_member("Alice", "alice@example.com", "9000000001")
    m2 = add_member("Bob", "bob@example.com", "9000000002")
    borrow_book(b1, m1, 7)
    borrow_book(b2, m2, 14)
    print("Sample data loaded.")


# ------------------------- CLI -------------------------

MENU = """
\n===== Library Management =====
1) Add Book
2) List/Search Books
3) Delete Book
4) Add Member
5) List/Search Members
6) Delete Member
7) Borrow Book
8) Return Book
9) Load Sample Data
10) View Active Loans
11) View All Loans
12) View Overdue Loans
13) Stats Summary
0) Exit
"""


def cli_loop():
    while True:
        print(MENU)
        choice = input_int("Choose an option: ", 0, 13)
        if choice == 0:
            print("Goodbye!")
            break
        elif choice == 1:
            title = input("Title: ")
            author = input("Author: ")
            isbn = input("ISBN (optional): ") or None
            copies = input_int("Total copies: ", 1)
            book_id = add_book(title, author, isbn, copies)
            print(f"Added book with ID {book_id}.")
        elif choice == 2:
            kw = input("Keyword (title/author/isbn, blank for all): ")
            rows = list_books(kw or None)
            print_rows(rows, headers=["id", "title", "author", "isbn", "copies_total", "copies_available", "created_at"])
        elif choice == 3:
            bid = input_int("Book ID to delete: ", 1)
            delete_book(bid)
        elif choice == 4:
            name = input("Name: ")
            email = input("Email (optional): ") or None
            phone = input("Phone (optional): ") or None
            member_id = add_member(name, email, phone)
            print(f"Added member with ID {member_id}.")
        elif choice == 5:
            kw = input("Keyword (name/email/phone, blank for all): ")
            rows = list_members(kw or None)
            print_rows(rows, headers=["id", "name", "email", "phone", "joined_at"])
        elif choice == 6:
            mid = input_int("Member ID to delete: ", 1)
            delete_member(mid)
        elif choice == 7:
            bid = input_int("Book ID: ", 1)
            mid = input_int("Member ID: ", 1)
            days = input_int("Loan duration (days, default 14): ", 1) or 14
            borrow_book(bid, mid, days)
        elif choice == 8:
            lid = input_int("Loan ID to return: ", 1)
            return_book(lid)
        elif choice == 9:
            load_sample_data()
        elif choice == 10:
            rows = list_loans(active_only=True)
            print_rows(rows, headers=["id", "book_title", "member_name", "loan_date", "due_date", "return_date"])
        elif choice == 11:
            rows = list_loans(active_only=False)
            print_rows(rows, headers=["id", "book_title", "member_name", "loan_date", "due_date", "return_date"])
        elif choice == 12:
            rows = list_overdue()
            print_rows(rows, headers=["id", "book_title", "member_name", "loan_date", "due_date"])
        elif choice == 13:
            b, m, a, o = stats()
            print(f"Books: {b} | Members: {m} | Active loans: {a} | Overdue: {o}")
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    init_db()
    cli_loop()
