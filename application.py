import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timezone

from helpers import apology, login_required, lookup, usd

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
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    rows = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id = session["user_id"])
    cash = rows[0]["cash"]
    total = cash

    stocks = db.execute("SELECT symbol, SUM(shares) as shares FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING SUM(shares) > 0", user_id = session["user_id"])

    quotes = {}
    values = {}
    for stock in stocks:
        quotes[stock["symbol"]] = lookup(stock["symbol"])
        values[stock["symbol"]] = usd(lookup(stock["symbol"])["price"] * stock["shares"])
        total += lookup(stock["symbol"])["price"]

    return render_template("portfolio.html", quotes=quotes, stocks=stocks, total=usd(total), cash=usd(cash), values=values)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        stock = lookup(symbol)

        try:
            shares = int(request.form.get("shares"))
        except:
            return apology("shares must be a positive integer", 400)

        if stock == None:
            return apology("invalid symbol", 400)
        if shares < 1:
            return apology("cannot buy less than or 0 shares")

        cost = stock["price"] * shares
        rows = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id = session["user_id"])
        cash = rows[0]["cash"]

        if cash < cost:
            return apology("not enough cash")

        now = str(datetime.now(timezone.utc).date()) + " " + datetime.now(timezone.utc).time().strftime("%H:%M:%S")

        db.execute("UPDATE users SET cash = cash - :cost WHERE id = :user_id", cost = cost, user_id = session["user_id"])
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price_per_share, time) VALUES (:user_id, :symbol, :shares, :price_per_share, :time)",
                    user_id = session["user_id"], symbol = symbol, shares = shares, price_per_share = stock["price"], time = now)

        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute("SELECT symbol, shares, price_per_share, time FROM transactions WHERE user_id = :user_id ORDER BY time DESC", user_id=session["user_id"])

    quotes = {}
    for stock in transactions:
        quotes[stock["symbol"]] = lookup(stock["symbol"])

    return render_template("history.html", quotes=quotes, transactions=transactions)


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
    if request.method == "POST":
        symbol = request.form.get("symbol")
        info = lookup(symbol)

        if not info:
            return render_template("quote.html", misquoted = True, symbol=symbol)

        return render_template("quoted.html", name=info["name"], symbol=info["symbol"], price=info["price"])

    else:
        return render_template("quote.html", misquoted = False)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)
        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)
        # Ensure password conformation is same as password
        elif not request.form.get("password") == request.form.get("confirmation"):
            return apology("passwords do not match", 400)

        password = request.form.get("password")

        if len(password) < 8:
            return apology("password must be at least 8 characters long")

        oneUpper = False
        oneNum = False

        for char in password:
            if char.isupper() == True:
                oneUpper = True
            if char.isdigit() == True:
                oneNum = True

        if oneUpper == False or oneNum == False:
            return apology("password must include one uppercase letter and one number")


        pwdhash = generate_password_hash(password)

        rows = db.execute("SELECT * FROM users WHERE username == :username", username=request.form.get("username"))

        if len(rows) != 0:
            return apology("username taken", 400)

        new_id = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                            username = request.form.get("username"), hash = pwdhash)

        session["user_id"] = new_id
        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        stock = lookup(symbol)

        try:
            shares = int(request.form.get("shares"))
        except:
            return apology("shares must be a positive integer", 400)

        if stock == None:
            return apology("invalid symbol", 400)
        if shares < 1:
            return apology("cannot sell less than or 0 shares")


        value = stock["price"] * shares
        rows = db.execute("SELECT SUM(shares) as shares FROM transactions WHERE user_id = :user_id AND symbol = :symbol", user_id = session["user_id"], symbol=symbol)
        shares_owned = rows[0]["shares"]
        if shares > shares_owned:
            return apology(f"you only have {shares_owned} shares of {symbol}", 400)

        now = str(datetime.now(timezone.utc).date()) + " " + datetime.now(timezone.utc).time().strftime("%H:%M:%S")

        db.execute("UPDATE users SET cash = cash + :value WHERE id = :user_id", value = value, user_id = session["user_id"])
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price_per_share, time) VALUES (:user_id, :symbol, :shares, :price_per_share, :time)",
                    user_id = session["user_id"], symbol = symbol, shares = -shares, price_per_share = stock["price"], time = now)

        return redirect("/")
    else:
        stocks = db.execute("SELECT symbol, SUM(shares) as shares FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING shares > 0", user_id = session["user_id"])
        return render_template("sell.html", stocks=stocks)

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)