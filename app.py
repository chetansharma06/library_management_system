from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "secret"
DATABASE = "database.db"

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # Books Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS books(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        author TEXT,
        serial_no TEXT UNIQUE,
        type TEXT,
        available INTEGER
    )
    """)

    # Issued Books Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS issued_books(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER,
        book_name TEXT,
        author TEXT,
        serial_no TEXT,
        issue_date TEXT,
        return_date TEXT,
        remarks TEXT,
        fine_calculated INTEGER DEFAULT 0,
        FOREIGN KEY(book_id) REFERENCES books(id)
    )
    """)

    # Members Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS members(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        membership_number TEXT UNIQUE,
        name TEXT,
        duration TEXT,
        status TEXT
    )
    """)

    # Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        type TEXT,
        password TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

@app.route("/", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # Dummy auth logic to keep it simple, hardcoded admin
        if username == "admin" and password == "admin":
            session["role"] = "admin"
            session["user_name"] = "Admin"
            return redirect("/dashboard")
        elif username and password:
            session["role"] = "user"
            session["user_name"] = username
            return redirect("/dashboard")
        else:
            error = "Invalid credentials"

    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/dashboard")
def dashboard():
    if "role" not in session: return redirect("/")
    return render_template("dashboard.html", role=session["role"])

# --- API ---
@app.route("/api/book/<name>")
def api_book(name):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT author, serial_no FROM books WHERE name=? AND available=1 LIMIT 1", (name,))
    data = cursor.fetchone()
    conn.close()
    if data:
        return jsonify({"found": True, "author": data["author"], "serial_no": data["serial_no"]})
    return jsonify({"found": False})

@app.route("/api/book_by_serial/<serial>")
def api_book_by_serial(serial):
    conn = get_db()
    cursor = conn.cursor()
    # Find active issue by serial
    cursor.execute("SELECT * FROM issued_books WHERE serial_no=? ORDER BY id DESC LIMIT 1", (serial,))
    data = cursor.fetchone()
    conn.close()
    if data:
        return jsonify({"found": True, "book_name": data["book_name"], "author": data["author"], "issue_date": data["issue_date"], "return_date": data["return_date"]})
    return jsonify({"found": False})

@app.route("/api/member/<mem_num>")
def api_member(mem_num):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM members WHERE membership_number=?", (mem_num,))
    data = cursor.fetchone()
    conn.close()
    if data:
        return jsonify({"found": True, "name": data["name"], "duration": data["duration"], "status": data["status"]})
    return jsonify({"found": False})


# --- TRANSACTIONS ---
@app.route("/issue_book", methods=["GET", "POST"])
def issue_book():
    if "role" not in session: return redirect("/")
    error = None
    if request.method == "POST":
        book_name = request.form.get("book_name")
        author = request.form.get("author")
        issue_date = request.form.get("issue_date")
        return_date = request.form.get("return_date")
        remarks = request.form.get("remarks")

        if not book_name or not author or not issue_date or not return_date:
            error = "Please fill completely or select a valid book feature."
        else:
            # Check issue date > today
            today = datetime.now().date()
            try:
               i_d = datetime.strptime(issue_date, "%Y-%m-%d").date()
            except:
               i_d = today
            
            if i_d < today:
                error = "Issue Date cannot be in the past."
            else:
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("SELECT id, serial_no FROM books WHERE name=? AND available=1 LIMIT 1", (book_name,))
                book = cursor.fetchone()
                
                if book:
                    b_id = book["id"]
                    s_no = book["serial_no"]
                    cursor.execute("""
                    INSERT INTO issued_books (book_id, book_name, author, serial_no, issue_date, return_date, remarks)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (b_id, book_name, author, s_no, issue_date, return_date, remarks))
                    cursor.execute("UPDATE books SET available=0 WHERE id=?", (b_id,))
                    conn.commit()
                    return redirect("/dashboard")
                else:
                    error = "Book not available!"
                conn.close()

    return render_template("issue_book.html", error=error)

@app.route("/return_book", methods=["GET", "POST"])
def return_book():
    if "role" not in session: return redirect("/")
    error = None
    if request.method == "POST":
        book_name = request.form.get("book_name")
        serial = request.form.get("serial_no")
        
        if not book_name or not serial:
            error = "All mandatory fields must be filled to make a valid selection of the feature."
        else:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM issued_books WHERE serial_no=? AND book_name=? ORDER BY id DESC LIMIT 1", (serial, book_name))
            issue = cursor.fetchone()
            
            if issue:
                r_date_str = request.form.get("return_date")
                try:
                   actual_return = datetime.strptime(r_date_str, "%Y-%m-%d").date()
                except:
                   actual_return = datetime.now().date()

                expected_return = datetime.strptime(issue["return_date"], "%Y-%m-%d").date()
                fine = 0
                if actual_return > expected_return:
                    fine = (actual_return - expected_return).days * 10
                
                session["pending_return_id"] = issue["id"]
                session["fine_amount"] = fine
                conn.close()
                return redirect("/fine")
            else:
                error = "Invalid book return details!"
            conn.close()

    return render_template("return_book.html", error=error)

@app.route("/fine", methods=["GET", "POST"])
def fine():
    if "role" not in session: return redirect("/")
    
    issue_id = session.get("pending_return_id")
    fine_amt = session.get("fine_amount", 0)
    
    if not issue_id: return redirect("/dashboard")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM issued_books WHERE id=?", (issue_id,))
    issue = cursor.fetchone()
    
    error = None
    if request.method == "POST":
        paid = request.form.get("paid")
        
        if fine_amt > 0 and not paid:
            error = "Paid fine check box needs to be selected to complete transaction!"
        else:
            cursor.execute("DELETE FROM issued_books WHERE id=?", (issue_id,))
            cursor.execute("UPDATE books SET available=1 WHERE id=?", (issue["book_id"],))
            conn.commit()
            conn.close()
            session.pop("pending_return_id", None)
            session.pop("fine_amount", None)
            return redirect("/dashboard")

    conn.close()
    return render_template("fine.html", fine=fine_amt, issue=issue, error=error)

# --- REPORTS ---
@app.route("/search_book", methods=["GET", "POST"])
def search_book():
    if "role" not in session: return redirect("/")
    
    books = []
    error = None
    if request.method == "POST":
        query = request.form.get("query", "").strip()
        criteria = request.form.get("criteria", "")
        
        if not query and not criteria:
            error = "Please fill in a text box or select a dropdown feature before searching."
        else:
            conn = get_db()
            cursor = conn.cursor()
            if criteria == "Author":
                cursor.execute("SELECT * FROM books WHERE available=1 AND author LIKE ?", (f"%{query}%",))
            else:
                cursor.execute("SELECT * FROM books WHERE available=1 AND name LIKE ?", (f"%{query}%",))
                
            books = cursor.fetchall()
            conn.close()
            
    return render_template("search_book.html", books=books, error=error)


# --- MAINTENANCE ---
@app.route("/add_book", methods=["GET", "POST"])
def add_book():
    if session.get("role") != "admin": return "Access Denied! You are not Admin."
    error = None
    if request.method == "POST":
        name = request.form.get("name")
        author = request.form.get("author")
        serial = request.form.get("serial_no")
        btype = request.form.get("type", "Book")
        
        if not name or not author or not serial or not btype:
            error = "All fields are mandatory!"
        else:
            conn = get_db()
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO books (name, author, serial_no, type, available) VALUES (?, ?, ?, ?, 1)", 
                               (name, author, serial, btype))
                conn.commit()
                return redirect("/dashboard")
            except sqlite3.IntegrityError:
                error = "Serial Number must be unique!"
            finally:
                conn.close()
    return render_template("add_book.html", error=error)

@app.route("/update_book", methods=["GET", "POST"])
def update_book():
    if session.get("role") != "admin": return "Access Denied! You are not Admin."
    error = None
    if request.method == "POST":
        serial = request.form.get("serial_no")
        name = request.form.get("name")
        author = request.form.get("author")
        btype = request.form.get("type", "Book")
        
        if not serial or not name or not author or not btype:
            error = "All fields are mandatory!"
        else:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE books SET name=?, author=?, type=? WHERE serial_no=?", (name, author, btype, serial))
            if cursor.rowcount == 0:
                error = "Book with this serial number not found."
            else:
                conn.commit()
                conn.close()
                return redirect("/dashboard")
            conn.close()
            
    return render_template("update_book.html", error=error)

@app.route("/membership", methods=["GET", "POST"])
def membership():
    if session.get("role") != "admin": return "Access Denied! You are not Admin."
    error = None
    if request.method == "POST":
        m_num = request.form.get("membership_number")
        name = request.form.get("name")
        duration = request.form.get("duration", "6 months")
        
        if not m_num or not name or not duration:
            error = "All fields are mandatory!"
        else:
            conn = get_db()
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO members (membership_number, name, duration, status) VALUES (?, ?, ?, 'Active')",
                               (m_num, name, duration))
                conn.commit()
                return redirect("/dashboard")
            except sqlite3.IntegrityError:
                error = "Membership number already exists!"
            finally:
                conn.close()
    return render_template("membership.html", error=error)

@app.route("/update_membership", methods=["GET", "POST"])
def update_membership():
    if session.get("role") != "admin": return "Access Denied! You are not Admin."
    error = None
    if request.method == "POST":
        m_num = request.form.get("membership_number")
        action = request.form.get("action")
        
        if not m_num:
            error = "Membership Number is mandatory to update."
        else:
            conn = get_db()
            cursor = conn.cursor()
            if action == "Extend":
                cursor.execute("UPDATE members SET status='Active', duration='6 months' WHERE membership_number=?", (m_num,))
            elif action == "Cancel":
                cursor.execute("UPDATE members SET status='Cancelled' WHERE membership_number=?", (m_num,))
            
            if cursor.rowcount == 0:
                error = "Member not found."
            else:
                conn.commit()
                return redirect("/dashboard")
            conn.close()
    return render_template("update_membership.html", error=error)

@app.route("/user", methods=["GET", "POST"])
def user_management():
    if session.get("role") != "admin": return "Access Denied! You are not Admin."
    error = None
    if request.method == "POST":
        utype = request.form.get("user_status", "NewUser")
        name = request.form.get("name")
        
        if not name:
            error = "Name is mandatory!"
        else:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (name, type, password) VALUES (?, ?, 'password')", (name, "user"))
            conn.commit()
            conn.close()
            return redirect("/dashboard")

    return render_template("user.html", error=error)

@app.route("/chart")
def chart():
    if "role" not in session: return redirect("/")
    return render_template("chart.html")


if __name__ == "__main__":
    app.run(debug=True)