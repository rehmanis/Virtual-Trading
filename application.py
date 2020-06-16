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
conn = psycopg2.connect( 
    database = url.path[1:],
    user = url.username,
    password = url.password,
    host = url.hostname,
    port = url.port
)


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    data = db.execute("SELECT username, cash FROM users WHERE id = :id", id=session["user_id"]);
    #username = data[0]["username"]
    print("----------")
    print(data)
    print("------------")
    cash = data[0]["cash"]
    summary = []
    total = cash
    dayChange = 0
    prevTotPrice = 0

    rows = db.execute("SELECT symbol, SUM(shares) FROM transcations WHERE id = :id GROUP BY symbol HAVING SUM(shares)>0",
                      id=session["user_id"])

    for row in rows:
        company_info = lookup(row["symbol"])
        entry = dict(name = company_info["name"], symbol = company_info["symbol"],
                     shares = row["SUM(shares)"], price = company_info["price"],
                     change = company_info["change"], changePercent = company_info["changePercent"])
        total += (entry["shares"] * entry["price"])
        dayChange += company_info["change"] * row["SUM(shares)"]
        prevTotPrice += company_info["previousClose"] * row["SUM(shares)"]
        summary.append(entry)

    percentPLDay = dayChange/prevTotPrice * 100

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
    data = db.execute("SELECT * FROM users WHERE id = :id", id=session["user_id"]);

    # ensure the current user has enough money to buy the shares
    if company_info["price"] * shares > data[0]["cash"]:
        return apology("Not enough cash to buy")

    # calculate and update the amount of cash left after buy the requested shares
    cash_left = data[0]["cash"] - (company_info["price"] * shares)

    db.execute("UPDATE users SET cash=? WHERE id=?", (cash_left, session["user_id"]))

    # store this transcation to buy the desired shares in a separate table
    db.execute("INSERT INTO transcations (id, username, symbol, shares, price, time) VALUES (?, ?, ?, ?, ?, ?)",
               session["user_id"], data[0]["username"], symbol, shares, company_info["price"], datetime.now())

    # redirect to the summary page to show the stock porfolio
    flash("Shares bought!")
    return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    rows = db.execute("SELECT * FROM transcations WHERE id = :id", id=session["user_id"])

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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

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

    exiting_row = db.execute("SELECT * FROM users WHERE username = :username",
                      username=curr_username)

    # ensure that username entered does not exist
    if exiting_row:
        return apology("username already exists", 403)

    # Query database for username
    user_id = db.execute("INSERT INTO users (username, hash) VALUES (?, ?)",
                      request.form.get("username"), password_hash)
    print("------------------")
    print("user_id")
    print (db.execute("SELECT * FROM users WHERE username = :username",
                      username=request.form.get("username")))

    print("---------------------")

    # Remember which user has logged in
    session["user_id"] = user_id
    flash("Successfully registered!")

    return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    data = db.execute("SELECT username, cash FROM users WHERE id = :id", id=session["user_id"]);
    username = data[0]["username"]
    cash = data[0]["cash"]

    if request.method == "GET":

        symbols = db.execute("SELECT symbol FROM transcations WHERE id = :id GROUP BY symbol HAVING SUM(shares) > 0",
              id=session["user_id"])

        return render_template("sell.html", symbols=symbols)


    if request.method == "POST":

        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))
        data = db.execute("SELECT symbol, SUM(shares) FROM transcations WHERE id = :id AND symbol = :symbol GROUP BY symbol",
              id=session["user_id"], symbol=symbol)

        if shares > data[0]["SUM(shares)"]:
            return apology("Not enough shares to sell")

        # lookup the company information such as share price, name etc.
        company_info = lookup(symbol)

        # make sure the company symbol that the user input was valid one
        if not company_info:
            return apology("Company Symbol is not a valid")


        # calculate and update the amount of cash left after buy the requested shares
        cash_left = cash + (company_info["price"] * shares)

        db.execute("UPDATE users SET cash=? WHERE id=?", (cash_left, session["user_id"]))

        # store this transcation to buy the desired shares in a separate table
        db.execute("INSERT INTO transcations (id, username, symbol, shares, price, time) VALUES (?, ?, ?, ?, ?, ?)",
                       session["user_id"], username, symbol, -shares, company_info["price"], datetime.now())

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
