import os

from cs50 import SQL
import sqlalchemy
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd
from datetime import datetime

import urllib.parse
import psycopg2
import psycopg2.extras
import decimal


START_CASH = 10000

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True




# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
print(os.environ["DATABASE_URL"])
db = SQL(os.environ["DATABASE_URL"])
#db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


urllib.parse.uses_netloc.append("postgres")
url = urllib.parse.urlparse(os.environ["DATABASE_URL"])
print("---------------")
print(url)
print("path: " + url.path[1:])
print (url.username)
print(url.password)
print("---------------------")
# conn = psycopg2.connect( 
#     database = url.path[1:],
#     user = url.username,
#     password = url.password,
#     host = url.hostname,
#     port = url.port
# )

with psycopg2.connect(database = url.path[1:], user = url.username,
    password = url.password, host = url.hostname, port = url.port) as conn:
    conn.autocommit = True
    cursor = conn.cursor(cursor_factory = psycopg2.extras.DictCursor)



@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    cursor.execute("SELECT username, cash FROM users WHERE id = %s", (session["user_id"], ));
    data = cursor.fetchall()
    # conn.commit()

    #username = data[0]["username"]
    print("----------")
    print(data)
    print("------------")
    cash = data[0]["cash"]
    summary = []
    total = cash
    dayChange = 0
    prevTotPrice = 0
    percentPLDay = 0.0;

    cursor.execute("SELECT symbol, SUM(shares) FROM transcations WHERE id = %s GROUP BY symbol HAVING SUM(shares)>0",
                      (session["user_id"],))
    rows = cursor.fetchall()

    print("-----")
    print(rows)
    print("-----")

    for row in rows:
        company_info = lookup(row["symbol"])
        entry = dict(name = company_info["name"], symbol = company_info["symbol"],
                     shares = int(row["sum"]), price = company_info["price"],
                     change = company_info["change"], changePercent = company_info["changePercent"])
        total += decimal.Decimal(entry["shares"] * entry["price"])
        dayChange += company_info["change"] * int(row["sum"])
        prevTotPrice += company_info["previousClose"] * int(row["sum"])
        summary.append(entry)

    if rows:
        percentPLDay = dayChange/prevTotPrice * 100

    print("--------")
    print(entry)
    print(dayChange)
    print(prevTotPrice)
    print(total)
    print("----------------------------")

    return render_template("index.html", rows=summary, cash=cash, total=total, start_cash=START_CASH, percentPLDay=percentPLDay)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "GET":
        return render_template("buy.html")

    ### User reached route via POST (as by submitting a form via POST) ###

    # store the values of shares the symbol inputed by the user
    shares = request.form.get("shares")
    symbol = request.form.get("symbol")

    # ensure that symbol is inputted by user
    if not symbol:
        return apology("Symbol field should not be empty")

    # enrue that number of shares to buy are inputted by user
    if not shares:
        return apology("Shares field should not be empty")

    shares = int(shares)
    symbol = symbol.upper()

    # lookup the company information such as share price, name etc.
    company_info = lookup(symbol)

    # make sure the company symbol that the user input was valid one
    if not company_info:
        return apology("Company Symbol is not a valid")

    # find the row of data for the current user
    cursor.execute("SELECT * FROM users WHERE id = %s", (session["user_id"], ));
    data = cursor.fetchall()

    # ensure the current user has enough money to buy the shares
    if company_info["price"] * shares > data[0]["cash"]:
        return apology("Not enough cash to buy")

    # calculate and update the amount of cash left after buy the requested shares
    cash_left = data[0]["cash"] - decimal.Decimal(company_info["price"] * shares)

    cursor.execute("UPDATE users SET cash=%s WHERE id=%s", (cash_left, session["user_id"]))

    # store this transcation to buy the desired shares in a separate table
    cursor.execute("INSERT INTO transcations (id, username, symbol, shares, price, time) VALUES (%s, %s, %s, %s, %s, %s)",
               (session["user_id"], data[0]["username"], symbol, shares, company_info["price"], datetime.now()))

    # redirect to the summary page to show the stock porfolio
    flash("Shares bought!")
    return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    cursor.execute("SELECT * FROM transcations WHERE id = %s", (session["user_id"], ))
    rows = cursor.fetchall()

    return render_template("history.html", rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        cursor.execute("SELECT * FROM users WHERE username = %s",
                          (request.form.get("username"),))
        rows = cursor.fetchall()

        print("----------")
        print(rows)
        print("----------")

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    if request.method == "GET":
        return render_template("quote.html")

    company_info = lookup(request.form.get("symbol"))

    if not company_info:
        return apology("invalid symbol", 403)

    return render_template("quoted.html", company_info=company_info)


@app.route("/register", methods=["GET", "POST"])
def register():

    # User reached the route via GET (when registering for the first time)
    if request.method == "GET":
        return render_template("register.html")

    # User reached route via POST (as by submitting a form via POST)

    curr_username = request.form.get("username")

    # Ensure username was submitted
    if not curr_username:
        return apology("must provide username", 403)

    # Ensure password was not blank
    if not request.form.get("password"):
        return apology("must provide password", 403)

    # Ensure the confirmation of password was not blank
    if not request.form.get("confirmation"):
        return apology("must confirm the password provided above", 403)

    password_hash = generate_password_hash(request.form.get("password"))

    # Ensure two password entered are same
    if not check_password_hash(password_hash, request.form.get("confirmation")):
        return apology("two passowrds do not match", 403)

    exiting_row = cursor.execute("SELECT * FROM users WHERE username = %s", (curr_username,))
    #conn.commit()

    # ensure that username entered does not exist
    if exiting_row:
        return apology("username already exists", 403)

    # Query database for username
    user_id = cursor.execute("INSERT INTO users (username, hash) VALUES (%s, %s)",
                      (request.form.get("username"), password_hash))
    #conn.commit()

    print("------------------")
    print(user_id)
    print(cursor.execute("SELECT * FROM users WHERE username = %s", (request.form.get("username"), )))
    #conn.commit()

    print("---------------------")

    # Remember which user has logged in
    session["user_id"] = user_id
    flash("Successfully registered!")

    return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    cursor.execute("SELECT username, cash FROM users WHERE id = %s", (session["user_id"], ));
    data = cursor.fetchall()
    username = data[0]["username"]
    cash = data[0]["cash"]

    if request.method == "GET":

        cursor.execute("SELECT symbol FROM transcations WHERE id = %s GROUP BY symbol HAVING SUM(shares) > 0",
              (session["user_id"], ))
        symbols = cursor.fetchall()
        return render_template("sell.html", symbols=symbols)


    if request.method == "POST":

        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))
        cursor.execute("SELECT symbol, SUM(shares) FROM transcations WHERE id = %s AND symbol = %s GROUP BY symbol",
              (session["user_id"], symbol))
        data = cursor.fetchall()

        if shares > data[0]["sum"]:
            return apology("Not enough shares to sell")

        # lookup the company information such as share price, name etc.
        company_info = lookup(symbol)

        # make sure the company symbol that the user input was valid one
        if not company_info:
            return apology("Company Symbol is not a valid")


        # calculate and update the amount of cash left after buy the requested shares
        cash_left = cash + decimal.Decimal(company_info["price"] * shares)

        cursor.execute("UPDATE users SET cash=%s WHERE id=%s", (cash_left, session["user_id"], ))

        # store this transcation to buy the desired shares in a separate table
        cursor.execute("INSERT INTO transcations (id, username, symbol, shares, price, time) VALUES (%s, %s, %s, %s, %s, %s)",
                       (session["user_id"], username, symbol, -shares, company_info["price"], datetime.now()))

        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)


if __name__ == "__main__":
    app.debug = True
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
