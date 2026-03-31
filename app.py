from flask import Flask, render_template, request, redirect, session
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "secret"

# ---------------- DATABASE ----------------
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # Books
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS books(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        author TEXT,
        available INTEGER
    )
    """)

    # Issued Books
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS issued_books(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_name TEXT,
        author TEXT,
        issue_date TEXT,
        return_date TEXT
    )
    """)

    # Members
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS members(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        duration TEXT
    )
    """)

    # Users
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        type TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ---------------- LOGIN ----------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]

        if username == "admin":
            session["role"] = "admin"
        else:
            session["role"] = "user"

        return redirect("/dashboard")

    return render_template("login.html")

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", role=session.get("role"))

# ---------------- ADD BOOK ----------------
@app.route("/add_book", methods=["GET", "POST"])
def add_book():
    if session.get("role") != "admin":
        return "Access Denied!"

    if request.method == "POST":
        name = request.form["name"]
        author = request.form["author"]

        if name == "" or author == "":
            return "All fields required!"

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("INSERT INTO books (name, author, available) VALUES (?, ?, 1)", (name, author))

        conn.commit()
        conn.close()

        return redirect("/dashboard")

    return render_template("add_book.html")

# ---------------- SEARCH BOOK ----------------
@app.route("/search_book")
def search_book():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM books WHERE available=1")
    books = cursor.fetchall()

    conn.close()
    return render_template("search_book.html", books=books)

# ---------------- ISSUE BOOK ----------------
@app.route("/issue_book", methods=["GET", "POST"])
def issue_book():
    if request.method == "POST":
        book_name = request.form["book_name"]

        if book_name == "":
            return "Enter book name!"

        issue_date = datetime.now().date()
        return_date = issue_date + timedelta(days=15)

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("SELECT author FROM books WHERE name=? AND available=1", (book_name,))
        data = cursor.fetchone()

        if data:
            author = data[0]

            cursor.execute("""
            INSERT INTO issued_books (book_name, author, issue_date, return_date)
            VALUES (?, ?, ?, ?)
            """, (book_name, author, issue_date, return_date))

            cursor.execute("UPDATE books SET available=0 WHERE name=?", (book_name,))
            conn.commit()
        else:
            return "Book not available!"

        conn.close()
        return redirect("/dashboard")

    return render_template("issue_book.html")

# ---------------- RETURN BOOK ----------------
@app.route("/return_book", methods=["GET", "POST"])
def return_book():
    if request.method == "POST":
        book_name = request.form["book_name"]
        serial = request.form["serial"]

        if book_name == "" or serial == "":
            return "All fields required!"

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("SELECT return_date FROM issued_books WHERE book_name=?", (book_name,))
        data = cursor.fetchone()

        if data:
            return_date = datetime.strptime(data[0], "%Y-%m-%d").date()
            today = datetime.now().date()

            fine = 0
            if today > return_date:
                fine = (today - return_date).days * 10

            session["fine"] = fine
            session["book"] = book_name
        else:
            return "Invalid book!"

        conn.close()
        return redirect("/fine")

    return render_template("return_book.html")

# ---------------- FINE ----------------
@app.route("/fine", methods=["GET", "POST"])
def fine():
    fine = session.get("fine", 0)

    if request.method == "POST":
        paid = request.form.get("paid")
        book = session.get("book")

        if fine > 0 and not paid:
            return "Please pay fine!"

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("DELETE FROM issued_books WHERE book_name=?", (book,))
        cursor.execute("UPDATE books SET available=1 WHERE name=?", (book,))

        conn.commit()
        conn.close()

        return redirect("/dashboard")

    return render_template("fine.html", fine=fine)

# ---------------- MEMBERSHIP ----------------
@app.route("/membership", methods=["GET", "POST"])
def membership():
    if session.get("role") != "admin":
        return "Access Denied!"

    if request.method == "POST":
        name = request.form["name"]
        duration = request.form["duration"]

        if name == "":
            return "All fields required!"

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("INSERT INTO members (name, duration) VALUES (?, ?)", (name, duration))

        conn.commit()
        conn.close()

        return redirect("/dashboard")

    return render_template("membership.html")

# ---------------- USER MANAGEMENT ----------------
@app.route("/user", methods=["GET", "POST"])
def user():
    if session.get("role") != "admin":
        return "Access Denied!"

    if request.method == "POST":
        name = request.form["name"]
        utype = request.form["type"]

        if name == "":
            return "Name required!"

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("INSERT INTO users (name, type) VALUES (?, ?)", (name, utype))

        conn.commit()
        conn.close()

        return redirect("/dashboard")

    return render_template("user.html")

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)