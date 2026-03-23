from flask import Flask, url_for, redirect, request, render_template, session, flash, jsonify
from datetime import datetime
# from livereload import Server
from flask_login import LoginManager, logout_user, login_user, login_required, UserMixin, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
# from itsdangerous import URLSafeTimedSerializer
import requests 
import sqlite3
import stripe
import os

from dotenv import load_dotenv

from flask_mail import Mail, Message


app = Flask(__name__)
app.config.update(
    MAIL_SERVER= "localhost",
    MAIL_PORT = 25, 
    MAIL_USE_TLS = False,
    MAIL_USE_SSL = False,
    MAIL_USERNAME = None,
    MAIL_PASSWORD = None,
    MAIL_DEFAULT_SENDER = ('RZA', 'info@rza.com')
                          
    
)

mail=Mail(app)




HOTEL_PRICES = {
    "Standard": 100,
    "Family": 150,
    "Safari": 300
}

ZOO_TICKET = 25


load_dotenv()
app.secret_key = "015b1e90e876f0c1e88c3a7e688b7f386783b608d60fb193b680c32d07f22ad6"
stripe.api_key=os.getenv("STRIPE_SECRET_KEY")
if not stripe.api_key:
    raise ValueError("STRIPE_SECRET_KEY not found in environment variables!")


# # Set up flask login
# login_manager = LoginManager()
# login_manager.init_app(app)
# login_manager.login_view = 'login'

# @login_manager.user_loader
# def load_user(user_id):
#     return User.query.get(int(user_id))

YOUR_DOMAIN = "http://127.0.0.1:10067"
def get_db():
    return sqlite3.connect("rza.db")

"""Create payment db + tables"""
def get_dbp():
    connect=sqlite3.connect("payments.db")
    connect.row_factory=sqlite3.Row
    return connect

def init_db():
    db=get_dbp()
    db.execute(
        #Check the syntax of this 
        """CREATE TABLE IF NOT EXISTS payments(  
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount INTEGER,
            status TEXT,
            strip_id TEXT)"""
    )
    db.commit()
    
@app.route("/")
def index():
    flash("Welcome")
    return render_template("index.html")

@app.route("/register", methods=["POST",  "GET"])
def register():
    flash("Welcome")
    if request.method=="POST":
        """ Create the new user with password """
        email = request.form.get('email')
        name = request.form.get('name')
        password = request.form.get('password')
        confirm = request.form.get('confirm_password')

        """Basic Validation to check the inputs are entered"""
        if not name or not email or not password or not confirm:
            flash("All fields are required")
            return redirect(url_for("register"))
        
        if password != confirm:
            flash("Passwords do not match")
            return redirect(url_for("register"))


        hashed_pw = generate_password_hash(password)
        db=get_db()
        try:
            db.execute(
                "INSERT INTO users(name, email, password) VALUES (?, ?, ?)",
                (name, email, hashed_pw)
            )
            db.commit()
        except Exception:
            flash("Email already registered")
            return redirect(url_for("register"))

        flash("Registration successful!")
        return redirect(url_for("index"))

    return render_template("register.html")


@app.route('/login', methods=['POST', 'GET'])
def login():
    if request.method == "POST":
       db=get_db()
       user=db.execute(
           "SELECT * FROM users WHERE email=?",
           (request.form["email"],)).fetchone()
       
       if user and check_password_hash(user[3], request.form["password"]):
           session["user_id"]=user[0]
           return redirect (url_for("index"))
       

    else:
        return render_template('login.html', error = "Invalid username or password")
        
    
    return render_template("login.html") 

# @app.route('/logout')
# def logout():
#     logout_user()
#     return redirect(url_for('index'))



@app.route("/hotel_booking", methods=["POST",  "GET"])
def hotel_booking():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    total_price = None
    if request.method == "POST":
        check_in = request.form["check_in"]
        check_out = request.form["check_out"]
        room_type = request.form["room"]
        
        d1 = datetime.strptime(check_in, "%Y-%m-%d")
        d2 = datetime.strptime(check_out, "%Y-%m-%d")
        
        nights = (d2-d1).days
        if nights <= 0:
            return render_template("hotel_booking.html", error = "Invalid dates")
        
        price_per_night = HOTEL_PRICES.get(room_type, 0)
        total_price = nights * price_per_night
        
        
        
        
        db=get_db()
        db.execute(
            "INSERT INTO hotel_booking (user_id, check_in, check_out, room_type, total_price) VALUES (?, ?, ?, ?, ?)",
            (session["user_id"], check_in, check_out, room_type, total_price))
        
        db.execute(
            "UPDATE users SET loyalty_points = loyalty_points + 10 WHERE id=?",
            (session["user_id"],))
        
        db.commit()
        return render_template(
            "hotel_booking.html", 
            total_price=total_price,
            room_type=room_type,
            nights=nights,
            check_in=check_in,
            check_out=check_out,
            stripe_amount = total_price,
            description = f"HOTEL BOOKING ({room_type} room for {nights} nights)")
        
    return render_template("hotel_booking.html")

    
    
    
@app.route("/zoo_booking", methods=["POST",  "GET"])
def zoo_booking():
    if "user_id" not in session:
        return redirect(url_for("login"))
    total_price = None
    if request.method == "POST":
        tickets = int(request.form["tickets"])
        visit_date = request.form["date"]
        
        total_price = tickets * ZOO_TICKET
        db=get_db()
        db.execute(
            """
            INSERT INTO zoo_booking 
            (user_id, visit_date, tickets, total_price) 
            VALUES (?, ?, ?, ?)
            """,
            (session["user_id"], visit_date,tickets, total_price))
        
        db.execute(
            "UPDATE users SET loyalty_points = loyalty_points + 10 WHERE id=?",
            (session["user_id"],))
        
        db.commit()
        
        return render_template(
            "zoo_booking.html",
            stripe_amount=total_price,
            description = f"Zoo Tickets ({tickets} tickets)"
                               )
    return render_template("zoo_booking.html", total_price=total_price)
    
    
@app.route("/create-checkout-session", methods = ["POST"])
def create_checkout_session():
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "No data received"}), 400
    
    amount = int(data["amount"])
    description = data["description"]
    
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "gbp",
                    "product_data": {
                        "name": description,
                    },
                    "unit_amount": amount * 100, # 100 pence/cents
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=YOUR_DOMAIN + "/payment-success",
            cancel_url= YOUR_DOMAIN + "/payment-cancel",
        )
        
        # save payment
        db=get_dbp()
        db.execute(
            "INSERT INTO payments (amount, status, strip_id) VALUES (?, ?, ?)",
            (amount, "created", checkout_session.id)
        )
        
        db.commit()
        return jsonify({"id": checkout_session.id})
    
    except Exception as e:
        print("Stripe error", e)
        return jsonify ({"error": str(e)}), 403
        

@app.route("/payment-success")
def payment_success():
    render_template("payment_success.html")

@app.route("/payment-cancel")
def payment_cancel():
    render_template("payment_cancel.html")




@app.route("/dashboard")
def dashboard():
    
    if "user_id" not in session:
        return redirect(url_for("login"))
    db=get_db()
    user = db.execute(
        "SELECT * FROM users WHERE id=?",
        (session["user_id"], )).fetchone()
    
    return render_template("dashboard.html", user=user)

@app.route("/educational-visit", methods = ["POST", "GET"])
def educational_visit():
    if request.method=="POST":
        school_name = request.form["school_name"]
        contact_name = request.form["contact_name"]
        email = request.form["email"]
        visit_date = request.form["visit_date"]
        students = request.form["students"]
        level = request.form["level"]
        message = request.form["message"]
        
        
        try:
            msg= Message(
                subject="Testing email subject!",
                recipients=[email]
            )
            
            msg.body= f""" TESTING
            Hello {contact_name}, 
            Thank you for your booking!.
            
            Here are your details:
            
            School/Organisation: {school_name}
            Visit date: {visit_date}
            Number of students: {students}
            
            
            Additional notes: {message if message  else 'None'}
            
            We look forward to welcoming you and your students!
            
            Best regards,
            RZA
        
        """
        
            mail.send(msg)
        
            flash("Your visit request is accepted")
        
        except Exception as e:
            print("error send email", e)
            flash("Visit accepted but email not sent", "warning")
        
        
        # print(school_name, cont)
        
        flash("Educational visit request submitted successfully!", "success")
        return redirect(url_for("educational_visit"))
    return render_template("educational_visit.html")




@app.route("/forgot")
def forgot():
    if "user_id" not in session:
        return redirect(url_for("login"))
    db=get_db()
    user = db.execute(
        "UPDATE users SET email = ? WHERE id=?",
            ("umar@gmail.com", session["user_id"]))
    
    db.commit()
    
    return render_template("index.html")


@app.route("/view-resources")
def view_resources():
    return render_template("view_resources.html")

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=10067)
        

