import os

import json
from flask import Flask, session, render_template,request, redirect, url_for, jsonify,flash
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
import requests

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))
apikey = os.getenv("API_KEY")


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login")
def login():
    if "username" in session:
        return render_template("dashboard.html",username=session["username"])  
    return render_template("login.html")

@app.route("/dashboard", methods=["POST","GET"])
def dashboard():
    if request.method == "POST":
        username = request.form.get("username").lower()
        password = request.form.get("password")
        try:
            data = db.execute("SELECT password FROM users WHERE username=:username",{"username":username}).fetchone()
            if data[0]==password:
                session["username"] = username
                return render_template("dashboard.html",username=session["username"])
            else:
                return("Incorrect Password")
        except:
            return "User not found!"
    else:
        if "username" in session:
            return render_template("dashboard.html", username=session["username"])        
        return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("username", None)
    return render_template("index.html")

@app.route("/register")
def register():
    if "username" in session:
        return "You are already logged in."
    return render_template("register.html")

@app.route("/registered", methods = ["POST"])
def registered():
    username = request.form.get("username").lower()
    fullname = request.form.get("fullname")
    password = request.form.get("password")
    
    try:
        db.execute("INSERT INTO users(fullname, username, password) VALUES (:fullname,:username, :password)", {"fullname":fullname, "username":username, "password":password})
        db.commit()
        success = "Registered Successfully !"
        return render_template("login.html", success=success)
    except:
        return "Username already exists.Try a different username!!"

@app.route("/search", methods=["POST"])
def search():

    search = request.form.get("search")
    search = "%"+ search + "%"
    
    if db.execute("SELECT * FROM books WHERE isbn LIKE :isbn OR LOWER(title) LIKE :title OR LOWER(author) LIKE :author",{"isbn":search, "title":search.lower(), "author":search.lower()}).rowcount == 0:
        return "No books found !"

    books = db.execute("SELECT * FROM books WHERE isbn LIKE :isbn OR LOWER(title) LIKE :title OR LOWER(author) LIKE :author ORDER BY title",{"isbn":search, "title":search.lower(), "author":search.lower()}).fetchall()
    return render_template("dashboard.html", books=books, username=session["username"])
    
@app.route("/books/<title>")        
def books(title):
    if "username" in session:
        details = db.execute("SELECT * FROM books WHERE title=:title", {"title":title}).fetchall()
        bookid = db.execute("SELECT id FROM books WHERE title=:title",{"title":title}).fetchone()[0]
        allreviews = db.execute("SELECT review, username,rating FROM reviews JOIN books ON reviews.book_id=books.id JOIN users ON reviews.user_id=users.id WHERE books.id=:bookid",{"bookid":bookid}).fetchall()
        isbn = details[0].isbn


        myrating = db.execute("SELECT AVG(reviews.rating) AS my_rating FROM books JOIN reviews ON books.id=reviews.book_id WHERE isbn=:isbn",{"isbn":isbn}).fetchall()
        result = dict(myrating[0].items())
        try:
            result['my_rating']= float('%.2f'%(result['my_rating']))
        except:
            result['my_rating']= None    
            

        reviewed=False
        for review in allreviews:
            if review.username == session["username"]:
                reviewed=True
                break
            reviewed=False

        res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": apikey, "isbns":isbn}).json()    
        avg_rating = res['books'][0]['average_rating']
        rating_count = res['books'][0]['work_ratings_count']

        res2 = requests.get("https://www.googleapis.com/books/v1/volumes?q=isbn:" + isbn).json()
        try:
            cover = res2["items"][0]["volumeInfo"]["imageLinks"]["thumbnail"]
        except:
            cover = None

        try:
            description = res2['items'][0]['volumeInfo']['description']
        except:
            description = None            

        return render_template('books.html',title=title, details=details[0],allreviews=allreviews, reviewed=reviewed, avg_rating=avg_rating, rating_count=rating_count, cover=cover, description=description, myrating=result['my_rating'])

 
@app.route("/review/<title>", methods=["POST"])
def review(title):
    if request.method =="POST":
        if "username" in session:

            details = db.execute("SELECT * FROM books WHERE title=:title", {"title":title}).fetchall()
            review = request.form.get("review")
            rating = request.form["star"]
            userid = db.execute("SELECT id FROM users WHERE username=:username",{"username":session["username"]}).fetchone()[0]
            bookid = db.execute("SELECT id FROM books WHERE title=:title",{"title":title}).fetchone()[0]

            db.execute("INSERT INTO reviews (review, user_id, book_id, rating) VALUES (:review, :userid, :bookid, :rating)",{"review":review, "userid":userid, "bookid":bookid, "rating":rating})
            db.commit()

            return redirect(url_for('books',title=title))

@app.route("/api/<isbn>")
def get_api(isbn):
    data = db.execute("SELECT title,author,year,isbn, COUNT(reviews.id) AS review_count, AVG(reviews.rating) AS average_score FROM books JOIN reviews ON books.id=reviews.book_id WHERE isbn=:isbn GROUP BY title,author,year,isbn",{"isbn":isbn}).fetchall()      

    if len(data)!=1:
        return jsonify({"Error": "Invalid ISBN"}), 422            

    result = dict(data[0].items())

    result['average_score']= float('%.2f'%(result['average_score']))
    return jsonify(result)

@app.route("/myreviews")
def myreviews():
    if "username" in session:
        myrev = db.execute("SELECT title,review FROM books JOIN reviews ON books.id=reviews.book_id JOIN users ON users.id=reviews.user_id WHERE username=:username",{"username": session['username']}).fetchall()
        return render_template('myreviews.html',myrev=myrev)
    else:
        return redirect(url_for('login'))    