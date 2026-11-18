"""
Personal Expense Tracker
A command-line expense management application with SQLite persistence.
"""

import csv
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "expenses.db"
CATEGORIES = [
    "Food", "Travel", "Shopping", "Bills", "Health",
    "Education", "Entertainment", "Other"
]


@dataclass
class Expense:
    id: Optional[int]
    expense_date: str
    product: str
    amount: Decimal
    category: str
    location: str
    note: str = ""


class ExpenseDatabase:
    """Handles all SQLite database operations."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.create_table()

    def connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def create_table(self):
        with self.connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    expense_date TEXT NOT NULL,
                    product TEXT NOT NULL,
                    amount TEXT NOT NULL,
                    category TEXT NOT NULL,
                    location TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_expenses_date "
                "ON expenses(expense_date)"
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_expenses_category "
                "ON expenses(category)"
            )

    @staticmethod
    def row_to_expense(row):
        return Expense(
            id=row["id"],
            expense_date=row["expense_date"],
            product=row["product"],
            amount=Decimal(row["amount"]),
            category=row["category"],
            location=row["location"],
            note=row["note"],
        )

    def add(self, expense: Expense):
        with self.connect() as con:
            cursor = con.execute("""
                INSERT INTO expenses
                (expense_date, product, amount, category, location, note)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                expense.expense_date, expense.product, str(expense.amount),
                expense.category, expense.location, expense.note
            ))
            return cursor.lastrowid

    def get_all(self):
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM expenses ORDER BY expense_date DESC, id DESC"
            ).fetchall()
        return [self.row_to_expense(row) for row in rows]

    def get_by_id(self, expense_id: int):
        with self.connect() as con:
            row = con.execute(
                "SELECT * FROM expenses WHERE id = ?", (expense_id,)
            ).fetchone()
        return self.row_to_expense(row) if row else None

    def update(self, expense: Expense):
        with self.connect() as con:
            cursor = con.execute("""
                UPDATE expenses
                SET expense_date = ?, product = ?, amount = ?,
                    category = ?, location = ?, note = ?
                WHERE id = ?
            """, (
                expense.expense_date, expense.product, str(expense.amount),
                expense.category, expense.location, expense.note, expense.id
            ))
            return cursor.rowcount > 0

    def delete(self, expense_id: int):
        with self.connect() as con:
            cursor = con.execute(
                "DELETE FROM expenses WHERE id = ?", (expense_id,)
            )
            return cursor.rowcount > 0

    def search(self, keyword: str = "", category: str = "",
               start_date: str = "", end_date: str = ""):
        query = "SELECT * FROM expenses WHERE 1=1"
        params = []

        if keyword:
            query += " AND (product LIKE ? OR location LIKE ? OR note LIKE ?)"
            pattern = f"%{keyword}%"
            params.extend([pattern, pattern, pattern])
        if category and category != "All":
            query += " AND category = ?"
            params.append(category)
        if start_date:
            query += " AND expense_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND expense_date <= ?"
            params.append(end_date)

        query += " ORDER BY expense_date DESC, id DESC"
        with self.connect() as con:
            rows = con.execute(query, params).fetchall()
        return [self.row_to_expense(row) for row in rows]

    def total_spending(self):
        with self.connect() as con:
            row = con.execute(
                "SELECT COALESCE(SUM(CAST(amount AS REAL)), 0) AS total "
                "FROM expenses"
            ).fetchone()
        return Decimal(str(row["total"])).quantize(Decimal("0.01"))

    def category_totals(self):
        with self.connect() as con:
            rows = con.execute("""
                SELECT category, SUM(CAST(amount AS REAL)) AS total, COUNT(*) AS count
                FROM expenses
                GROUP BY category
                ORDER BY total DESC
            """).fetchall()
        return rows

    def monthly_totals(self, year: int):
        with self.connect() as con:
            rows = con.execute("""
                SELECT strftime('%m', expense_date) AS month,
                       SUM(CAST(amount AS REAL)) AS total,
                       COUNT(*) AS count
                FROM expenses
                WHERE strftime('%Y', expense_date) = ?
                GROUP BY month
                ORDER BY month
            """, (str(year),)).fetchall()
        return rows

    def export_csv(self, destination: Path):
        expenses = self.get_all()
        with destination.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow([
                "ID", "Date", "Product", "Amount", "Category",
                "Location", "Note"
            ])
            for item in expenses:
                writer.writerow([
                    item.id, item.expense_date, item.product, item.amount,
                    item.category, item.location, item.note
                ])
        return len(expenses)


class ExpenseTracker:
    """Contains the command-line interface and user workflows."""

    def __init__(self):
        self.database = ExpenseDatabase()

    @staticmethod
    def money(value: Decimal):
        return f"₹{value:,.2f}"

    @staticmethod
    def read_non_empty(prompt: str, default: str = ""):
        while True:
            value = input(prompt).strip()
            if value:
                return value
            if default:
                return default
            print("This field cannot be empty.")

    @staticmethod
    def read_date(prompt: str, default_today: bool = False):
        while True:
            raw = input(prompt).strip()
            if not raw and default_today:
                return date.today().isoformat()
            try:
                return datetime.strptime(raw, "%Y-%m-%d").date().isoformat()
            except ValueError:
                print("Enter a valid date in YYYY-MM-DD format.")

    @staticmethod
    def read_amount(prompt: str):
        while True:
            raw = input(prompt).strip().replace(",", "")
            try:
                amount = Decimal(raw)
                if not amount.is_finite() or amount <= 0:
                    raise InvalidOperation
                return amount.quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError):
                print("Enter a valid amount greater than zero.")

    @staticmethod
    def choose_category(current: str = ""):
        print("\nCategories:")
        for index, category in enumerate(CATEGORIES, start=1):
            print(f"{index}. {category}")
        if current:
            print(f"Current category: {current}")
        while True:
            raw = input("Choose category number: ").strip()
            if not raw and current:
                return current
            if raw.isdigit() and 1 <= int(raw) <= len(CATEGORIES):
                return CATEGORIES[int(raw) - 1]
            print(f"Choose a number from 1 to {len(CATEGORIES)}.")

    def add_expense(self):
        print("\n--- Add Expense ---")
        expense = Expense(
            id=None,
            expense_date=self.read_date("Date (YYYY-MM-DD, Enter for today): ", True),
            product=self.read_non_empty("Product / description: "),
            amount=self.read_amount("Amount (INR): "),
            category=self.choose_category(),
            location=input("Location (optional): ").strip(),
            note=input("Note (optional): ").strip(),
        )
        expense_id = self.database.add(expense)
        print(f"Expense added successfully. ID: {expense_id}")

    def display_expenses(self, expenses):
        if not expenses:
            print("\nNo expenses found.")
            return
        print("\n" + "-" * 91)
        print(f"{'ID':<5}{'Date':<13}{'Product':<22}{'Category':<17}{'Amount':>13}  Location")
        print("-" * 91)
        for item in expenses:
            product = item.product[:20]
            location = item.location[:18]
            print(
                f"{item.id:<5}{item.expense_date:<13}{product:<22}"
                f"{item.category:<17}{self.money(item.amount):>13}  {location}"
            )
        print("-" * 91)
        print(f"Records: {len(expenses)}")

    def view_expenses(self):
        self.display_expenses(self.database.get_all())

    def show_total(self):
        total = self.database.total_spending()
        print(f"\nTotal spending: {self.money(total)}")

    def category_report(self):
        rows = self.database.category_totals()
        if not rows:
            print("\nNo expenses available for a report.")
            return
        print("\n--- Spending by Category ---")
        for row in rows:
            total = Decimal(str(row["total"])).quantize(Decimal("0.01"))
            print(f"{row['category']:<18} {self.money(total):>14}  ({row['count']} records)")

    def monthly_report(self):
        current_year = date.today().year
        raw = input(f"Enter year (Enter for {current_year}): ").strip()
        try:
            year = int(raw) if raw else current_year
            if year < 1900 or year > 9999:
                raise ValueError
        except ValueError:
            print("Please enter a valid year.")
            return

        rows = self.database.monthly_totals(year)
        print(f"\n--- Monthly Report: {year} ---")
        if not rows:
            print("No expenses found for this year.")
            return
        month_names = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        year_total = Decimal("0.00")
        for row in rows:
            total = Decimal(str(row["total"])).quantize(Decimal("0.01"))
            year_total += total
            month_name = month_names[int(row["month"]) - 1]
            print(f"{month_name:<12} {self.money(total):>14}  ({row['count']} records)")
        print("-" * 30)
        print(f"{'Year total':<12} {self.money(year_total):>14}")

    def search_expenses(self):
        print("\n--- Search / Filter Expenses ---")
        keyword = input("Search product, location, or note (optional): ").strip()
        category = input("Category (exact name, or Enter for all): ").strip()
        start_date = input("From date YYYY-MM-DD (optional): ").strip()
        end_date = input("To date YYYY-MM-DD (optional): ").strip()

        try:
            if start_date:
                start_date = datetime.strptime(start_date, "%Y-%m-%d").date().isoformat()
            if end_date:
                end_date = datetime.strptime(end_date, "%Y-%m-%d").date().isoformat()
            if start_date and end_date and start_date > end_date:
                print("From date cannot be after To date.")
                return
        except ValueError:
            print("Invalid date. Use YYYY-MM-DD.")
            return

        if category and category not in CATEGORIES:
            print("Unknown category. Use one of the listed categories.")
            return
        results = self.database.search(keyword, category, start_date, end_date)
        self.display_expenses(results)

    def update_expense(self):
        try:
            expense_id = int(input("Enter expense ID to update: ").strip())
        except ValueError:
            print("Enter a valid numeric ID.")
            return
        old = self.database.get_by_id(expense_id)
        if not old:
            print("Expense ID not found.")
            return

        print("Press Enter to keep the current value.")
        new_date = self.read_date(f"Date [{old.expense_date}]: ") if input(
            f"Change date? Current is {old.expense_date} (y/N): "
        ).strip().lower() == "y" else old.expense_date
        product = input(f"Product [{old.product}]: ").strip() or old.product
        amount_raw = input(f"Amount [{old.amount}]: ").strip()
        if amount_raw:
            try:
                amount = Decimal(amount_raw.replace(",", ""))
                if not amount.is_finite() or amount <= 0:
                    raise InvalidOperation
                amount = amount.quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError):
                print("Invalid amount. Update cancelled.")
                return
        else:
            amount = old.amount

        change_category = input(f"Change category? Current: {old.category} (y/N): ").strip().lower()
        category = self.choose_category(old.category) if change_category == "y" else old.category
        location = input(f"Location [{old.location}]: ").strip() or old.location
        note = input(f"Note [{old.note}]: ").strip() or old.note

        updated = Expense(expense_id, new_date, product, amount, category, location, note)
        if self.database.update(updated):
            print("Expense updated successfully.")

    def delete_expense(self):
        try:
            expense_id = int(input("Enter expense ID to delete: ").strip())
        except ValueError:
            print("Enter a valid numeric ID.")
            return
        expense = self.database.get_by_id(expense_id)
        if not expense:
            print("Expense ID not found.")
            return
        print(f"{expense.product} - {self.money(expense.amount)} - {expense.expense_date}")
        confirm = input("Are you sure you want to delete this expense? (y/N): ").strip().lower()
        if confirm == "y":
            self.database.delete(expense_id)
            print("Expense deleted successfully.")
        else:
            print("Delete cancelled.")

    def export_csv(self):
        filename = f"expenses_export_{date.today().isoformat()}.csv"
        destination = BASE_DIR / filename
        count = self.database.export_csv(destination)
        print(f"Exported {count} expense(s) to: {destination.name}")

    @staticmethod
    def show_menu():
        print("""
========== PERSONAL EXPENSE TRACKER ==========
1. Add Expense
2. View All Expenses
3. View Total Spending
4. Spending by Category
5. Monthly Report
6. Search / Filter Expenses
7. Update Expense
8. Delete Expense
9. Export Expenses to CSV
0. Exit
==============================================
""")

    def run(self):
        actions = {
            "1": self.add_expense,
            "2": self.view_expenses,
            "3": self.show_total,
            "4": self.category_report,
            "5": self.monthly_report,
            "6": self.search_expenses,
            "7": self.update_expense,
            "8": self.delete_expense,
            "9": self.export_csv,
        }
        print("Welcome to Personal Expense Tracker.")
        print(f"Database: {DB_PATH.name}")
        while True:
            self.show_menu()
            choice = input("Choose an option: ").strip()
            if choice == "0":
                print("Thank you for using Personal Expense Tracker.")
                break
            action = actions.get(choice)
            if action:
                try:
                    action()
                except sqlite3.Error as error:
                    print(f"Database error: {error}")
                except KeyboardInterrupt:
                    print("\nOperation cancelled.")
            else:
                print("Invalid choice. Select an option from 0 to 9.")


def main():
    try:
        ExpenseTracker().run()
    except KeyboardInterrupt:
        print("\nApplication closed.")


if __name__ == "__main__":
    main()
