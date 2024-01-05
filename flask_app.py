import requests
import secrets
import random
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, session, url_for, redirect
import mysql.connector
import hashlib

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

db_config = {
    "host": "fransiskuspastoriko.mysql.pythonanywhere-services.com",
    "user": "fransiskuspastor",
    "password": "mysql123",
    "database": "fransiskuspastor$KotlandQuizApp",
}


def hash_password(password):
    hash_object = hashlib.sha256(password.encode())
    hashed_password = hash_object.hexdigest()
    return hashed_password


def get_background_image(hour):
    if (0 <= int(hour) <= 5) or (19 <= int(hour) <= 24):
        return "night"
    elif 6 <= int(hour) <= 10:
        return "morning"
    elif 11 <= int(hour) <= 15:
        return "day"
    elif 16 <= int(hour) <= 18:
        return "afternoon"
    else:
        return "error"


def get_local_hour(dt, offset):
    ts = dt + offset
    return int(datetime.utcfromtimestamp(ts).strftime("%H"))


def get_weather(city):
    api_key = "034ebfc05b59e770cd6537f1ffa97c1b"
    url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={api_key}"

    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        forecasts = []

        for day_data in data["list"]:
            temp_day = round(day_data["main"]["temp"] - 273.15)
            state_day = day_data["weather"][0]["description"]
            icon_code_day = day_data["weather"][0]["icon"]
            icon_url_day = f"http://openweathermap.org/img/wn/{icon_code_day}@4x.png"
            dt_day = int(day_data["dt"])
            offset = int(data["city"]["timezone"])
            date_time_day = datetime.utcfromtimestamp(dt_day + offset).strftime("%A, %B %d %Y, %H:%M")
            local_hour = get_local_hour(dt_day, offset)
            time_of_day = get_background_image(local_hour)

            forecasts.append(
                {
                    "temp": temp_day,
                    "state": state_day,
                    "icon_url": icon_url_day,
                    "date_time": date_time_day,
                    "time_of_day": time_of_day,
                }
            )

        return {"forecasts": forecasts, "city": city}
    else:
        forecasts = []
        local_hour = int(datetime.now().strftime("%H"))
        local_hour = (local_hour + 7) % 24
        current_time = datetime.utcnow() + timedelta(hours=local_hour + 7)
        date_time_day = current_time.strftime("%A, %B %d %Y, %H:%M")
        time_of_day = get_background_image(local_hour)
        forecasts.append(
            {
                "temp": 0,
                "state": "null",
                "icon_url": "http://openweathermap.org/img/wn/01d@4x.png",
                "date_time": date_time_day,
                "time_of_day": time_of_day,
            }
        )
        return {"forecasts": forecasts, "city": "City doesn't exist"}


def fetch_questions_from_database():
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor()

    select_query = (
        "SELECT id, question, option1, option2, option3, option4 FROM question"
    )
    cursor.execute(select_query)
    questions = cursor.fetchall()

    connection.close()

    quiz_database = []
    for q in questions:
        quiz_database.append(
            {
                "id": q[0],
                "question": q[1],
                "options": [q[2], q[3], q[4], q[5]],
            }
        )

    return quiz_database


def get_random_question(used_questions):
    unused_questions = [q for q in quiz_database if q["question"] not in used_questions]
    if not unused_questions:
        return None
    question = random.choice(unused_questions)
    return question

def get_city_from_ip(ip_address):
    api_key = '6788f3375003426fa589d7a087219a21'
    api_url = f'https://api.ipgeolocation.io/ipgeo/?apiKey={api_key}&ip={ip_address}'

    try:
        response = requests.get(api_url)
        data = response.json()

        city = data.get('city', 'City information not available')
        return city

    except requests.exceptions.RequestException as e:
        return f'Error: {e}'

quiz_database = fetch_questions_from_database()


@app.route("/register/", methods=["GET", "POST"])
def register():
    if "logged_in" in session and session["logged_in"]:
        return redirect("/home")

    if request.method == "GET":
        return render_template("register.html", error=False)

    username = request.form["username"]
    password = request.form["password"]
    confirm_password = request.form["confirm_password"]

    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor()

    check_username_query = "SELECT * FROM `register` WHERE username = %s"
    cursor.execute(check_username_query, (username,))
    existing_user = cursor.fetchone()

    if existing_user:
        connection.close()
        return render_template(
            "register.html", error=True, message="Username already taken"
        )

    if password != confirm_password:
        connection.close()
        return render_template(
            "register.html", error=True, message="Passwords do not match"
        )

    hashed_password = hash_password(password)

    insert_query = "INSERT INTO `register` (`username`, `password`) VALUES (%s, %s)"
    cursor.execute(insert_query, (username, hashed_password))

    connection.commit()
    connection.close()

    return redirect("/")


@app.route("/login/", methods=["GET", "POST"])
def login():
    if "logged_in" in session and session["logged_in"]:
        return redirect("/home")

    if request.method == "GET":
        return render_template("login.html", error=False)

    entered_username = request.form["username"]
    entered_password = request.form["password"]

    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor()

    select_query = "SELECT password FROM `register` WHERE username = %s"
    cursor.execute(select_query, (entered_username,))
    result = cursor.fetchone()

    connection.close()

    if result:
        hashed_entered_password = hash_password(entered_password)

        if hashed_entered_password == result[0]:
            session["logged_in"] = True
            session["username"] = entered_username
            connection.close()
            return redirect("/home")
        else:
            return render_template(
                "login.html", error=True, message="Incorrect password"
            )

    return render_template("login.html", error=True, message="Username not found")


@app.route("/", methods=["GET", "POST"])
def index():
    weather_data = None

    if request.environ.get("HTTP_X_FORWARDED_FOR") is None:
        public_ip = request.environ["REMOTE_ADDR"]
    else:
        public_ip = request.environ["HTTP_X_FORWARDED_FOR"]
    current_city = session.get('current_city') or get_city_from_ip(public_ip) or 'Jakarta'
    #current_city = session.get("current_city") or "Jakarta"

    if request.method == "POST":
        city = request.form["city"]
        session["current_city"] = city
    else:
        city = current_city

    weather_data = get_weather(city)

    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor()

    select_leaderboard_query = (
    "SELECT username, final_score, DATE(date) as date FROM result ORDER BY final_score DESC"
    )
    select_leaderboard_total_query = (
        "SELECT username, SUM(final_score) as total_score FROM result GROUP BY username ORDER BY SUM(final_score) DESC"
    )

    cursor.execute(select_leaderboard_query)
    leaderboard_data = [
        {"username": username, "final_score": final_score, "date": date}
        for username, final_score, date in cursor.fetchall()
    ]

    cursor_total = connection.cursor()
    cursor_total.execute(select_leaderboard_total_query)
    total_leaderboard_data = [
        {"username": username, "total_score": total_score}
        for username, total_score in cursor_total.fetchall()
    ]

    cursor.close()
    cursor_total.close()
    connection.close()

    return render_template(
        "index.html", weather_data=weather_data, leaderboard_data=leaderboard_data,total_leaderboard_data=total_leaderboard_data
    )


@app.route("/home", methods=["GET", "POST"])
def home():
    session.pop("quiz_score", None)
    if "logged_in" not in session or not session["logged_in"]:
        return redirect(url_for("login"))
    weather_data = None

    if request.environ.get("HTTP_X_FORWARDED_FOR") is None:
        public_ip = request.environ["REMOTE_ADDR"]
    else:
        public_ip = request.environ["HTTP_X_FORWARDED_FOR"]
    current_city = session.get('current_city') or get_city_from_ip(public_ip) or 'Jakarta'
    #current_city = session.get("current_city") or "Jakarta"

    if request.method == "POST":
        city = request.form["city"]
        session["current_city"] = city
    else:
        city = current_city

    weather_data = get_weather(city)

    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor()

    select_leaderboard_query = (
    "SELECT username, final_score, DATE(date) as date FROM result ORDER BY final_score DESC"
    )
    select_leaderboard_total_query = (
        "SELECT username, SUM(final_score) as total_score FROM result GROUP BY username ORDER BY SUM(final_score) DESC"
    )

    cursor.execute(select_leaderboard_query)
    leaderboard_data = [
        {"username": username, "final_score": final_score, "date": date}
        for username, final_score, date in cursor.fetchall()
    ]

    cursor_total = connection.cursor()
    cursor_total.execute(select_leaderboard_total_query)
    total_leaderboard_data = [
        {"username": username, "total_score": total_score}
        for username, total_score in cursor_total.fetchall()
    ]

    cursor.close()
    cursor_total.close()
    connection.close()

    return render_template(
        "home.html",
        weather_data=weather_data,
        leaderboard_data=leaderboard_data,
        total_leaderboard_data=total_leaderboard_data,
        username=session["username"],
    )


@app.route("/quiz", methods=["GET", "POST"])
def quiz():
    if "logged_in" not in session or not session["logged_in"]:
        return redirect(url_for("login"))
    if request.method == "GET":
        session["quiz_score"] = 0
        session["used_questions"] = list()

        question = get_random_question(session["used_questions"])
        if question is None:
            return "All questions have been used. Restart the server to reset."
        correct_answer = question["options"][0]
        options = random.sample(question["options"], len(question["options"]))
        session["used_questions"].append(question["question"])
        return render_template(
            "quiz.html",
            question=question,
            options=options,
            question_index=1,
            correct_answer=correct_answer,
            total_questions=20,
            username=session["username"],
        )
    elif request.method == "POST":
        question_index = int(request.form.get("question_index", 1))

        selected_answer = request.form.get("selected_answer")
        correct_answer = request.form.get("correct_answer")
        is_correct = selected_answer == correct_answer

        if is_correct:
            session["quiz_score"] += 1

        question = get_random_question(session["used_questions"])
        if len(quiz_database) == len(session["used_questions"]):
            return redirect(url_for("result"))
        new_correct_answer = question["options"][0]
        options = random.sample(question["options"], len(question["options"]))
        if question_index == 20:
            return redirect(url_for("result"))
        question_index += 1
        used_questions_set = set(session["used_questions"])
        used_questions_set.add(question["question"])
        session["used_questions"] = list(used_questions_set)

        return render_template(
            "quiz.html",
            question=question,
            options=options,
            question_index=question_index,
            total_questions=20,
            correct_answer=new_correct_answer,
            check=session["used_questions"],
            username=session["username"],
        )


@app.route("/result")
def result():
    if "logged_in" not in session or not session["logged_in"]:
        return redirect(url_for("login"))

    if "quiz_score" in session:
        final_score = (session["quiz_score"] / 20) * 100
    else:
        return render_template(
            "result.html",
            message="Quiz score not found. Please complete the quiz first.",
            username=session["username"],
        )

    if request.method == "GET":
        username = session.get("username")

        wib_timezone = timezone(timedelta(hours=7))
        current_date = datetime.now(wib_timezone).strftime("%Y-%m-%d %H:%M:%S")

        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        insert_result_query = "INSERT INTO `result` (`username`, `final_score`, `date`) VALUES (%s, %s, %s)"
        cursor.execute(insert_result_query, (username, final_score, current_date))

        connection.commit()
        connection.close()
        session.pop("quiz_score", None)

        return render_template(
            "result.html", final_score=final_score, username=session["username"], date_wib=current_date
        )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
