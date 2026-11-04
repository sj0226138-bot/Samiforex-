import os
import json
import requests
import smtplib

from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


# =====================================
# SAMIFOREX NEWS ALERT ENGINE
# =====================================

FMP_API_KEY = os.getenv("FMP_API_KEY")

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")

STATE_FILE = "alert_history.json"

FMP_URL = (
    "https://financialmodelingprep.com/stable/"
    "economic-calendar"
)

IMPORTANT_KEYWORDS = [
    "CPI",
    "INFLATION",
    "NONFARM",
    "NON-FARM",
    "PAYROLL",
    "UNEMPLOYMENT",
    "FEDERAL FUNDS",
    "INTEREST RATE",
    "FOMC",
    "GDP",
    "PCE",
    "CORE PCE",
    "RETAIL SALES",
    "PPI"
]


# =====================================
# TIME
# =====================================

def current_time():
    return datetime.now(timezone.utc)


def parse_event_time(value):
    try:
        return datetime.strptime(
            value,
            "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=timezone.utc)

    except ValueError:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        ).astimezone(timezone.utc)


def nigeria_time(value):
    return value.astimezone(
        timezone(timedelta(hours=1))
    ).strftime("%Y-%m-%d %I:%M %p")


# =====================================
# ALERT HISTORY
# =====================================

def load_history():
    if not os.path.exists(STATE_FILE):
        return []

    try:
        with open(STATE_FILE, "r") as file:
            return json.load(file)

    except Exception:
        return []


def save_history(history):
    with open(STATE_FILE, "w") as file:
        json.dump(history, file)


# =====================================
# FETCH ECONOMIC CALENDAR
# =====================================

def get_calendar():

    if not FMP_API_KEY:
        raise ValueError("FMP_API_KEY is missing.")

    today = current_time().date()
    future = today + timedelta(days=7)

    params = {
        "from": today.isoformat(),
        "to": future.isoformat(),
        "apikey": FMP_API_KEY
    }

    response = requests.get(
        FMP_URL,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise ValueError(
            f"Unexpected FMP response: {data}"
        )

    return data


# =====================================
# FILTER IMPORTANT US EVENTS
# =====================================

def important_event(event):

    name = str(event.get("event", "")).upper()

    currency = str(
        event.get("currency", "")
    ).upper()

    impact = str(
        event.get("impact", "")
    ).lower()

    if currency != "USD":
        return False

    if impact not in ["high", "medium"]:
        return False

    return any(
        word in name
        for word in IMPORTANT_KEYWORDS
    )


# =====================================
# ANALYSE ECONOMIC NEWS
# =====================================

def analyse_event(event):

    name = str(event.get("event", "")).upper()

    actual = event.get("actual")
    estimate = event.get("estimate")
    previous = event.get("previous")

    if actual is None or estimate is None:

        return (
            "NEUTRAL / WAIT",
            "Actual and forecast data are incomplete."
        )

    try:
        actual = float(actual)
        estimate = float(estimate)

    except (ValueError, TypeError):

        return (
            "NEUTRAL / WAIT",
            "The economic figures could not be compared."
        )

    if actual == estimate:

        return (
            "NEUTRAL",
            "Actual data matched the forecast."
        )

    actual_above = actual > estimate

    # Higher inflation generally supports USD.
    if any(word in name for word in [
        "CPI",
        "INFLATION",
        "PCE",
        "PPI"
    ]):

        usd_stronger = actual_above

    # Higher unemployment generally weakens USD.
    elif "UNEMPLOYMENT" in name:

        usd_stronger = not actual_above

    # Stronger employment generally supports USD.
    elif any(word in name for word in [
        "NONFARM",
        "NON-FARM",
        "PAYROLL",
        "RETAIL SALES",
        "GDP"
    ]):

        usd_stronger = actual_above

    else:

        return (
            "NEUTRAL / WAIT",
            "This event requires additional economic context."
        )

    if usd_stronger:

        bias = "USD BULLISH"

        explanation = (
            "The result is stronger than forecast. "
            "This may put downward pressure on Gold. "
            "Bitcoin's reaction is less predictable."
        )

    else:

        bias = "USD BEARISH"

        explanation = (
            "The result is weaker than forecast. "
            "This may support Gold. "
            "Bitcoin could benefit from a weaker USD, "
            "but confirmation is needed."
        )

    return bias, explanation


# =====================================
# SEND EMAIL
# =====================================

def send_email(subject, message):

    if not all([
        EMAIL_ADDRESS,
        EMAIL_PASSWORD,
        RECEIVER_EMAIL
    ]):

        raise ValueError(
            "Email settings are incomplete."
        )

    email = MIMEMultipart()

    email["From"] = EMAIL_ADDRESS
    email["To"] = RECEIVER_EMAIL
    email["Subject"] = subject

    email.attach(
        MIMEText(message, "plain")
    )

    with smtplib.SMTP(
        "smtp.gmail.com",
        587
    ) as server:

        server.starttls()

        server.login(
            EMAIL_ADDRESS,
            EMAIL_PASSWORD
        )

        server.send_message(email)


# =====================================
# MAIN ENGINE
# =====================================

def run_engine():

    print("SAMIFOREX News Engine started.")

    history = load_history()

    events = get_calendar()

    now = current_time()

    for event in events:

        if not important_event(event):
            continue

        event_name = event.get(
            "event",
            "Unknown event"
        )

        event_date = parse_event_time(
            event["date"]
        )

        event_id = (
            str(event_date)
            + "_"
            + event_name
        )

        # ---------------------------------
        # 30-MINUTE PRE-NEWS ALERT
        # ---------------------------------

        minutes_until = (
            event_date - now
        ).total_seconds() / 60

        pre_id = event_id + "_PRE"

        if (
            0 < minutes_until <= 30
            and pre_id not in history
        ):

            message = f"""
SAMIFOREX PRE-NEWS ALERT

Economic event: {event_name}

Scheduled time (Nigeria):
{nigeria_time(event_date)}

Time remaining:
Approximately {int(minutes_until)} minutes.

Markets:
XAUUSD - Gold
BTCUSD - Bitcoin

Status:
WAIT FOR RELEASE.

No guaranteed direction is assumed
before the economic figures are published.

This is a market-information alert,
not a trading instruction.
"""

            send_email(
                "SAMIFOREX: Upcoming US Economic News",
                message
            )

            history.append(pre_id)

            save_history(history)

            print(
                "Pre-news alert sent:",
                event_name
            )

        # ---------------------------------
        # POST-NEWS ANALYSIS
        # ---------------------------------

        actual = event.get("actual")

        post_id = event_id + "_POST"

        if (
            actual is not None
            and event_date <= now
            and post_id not in history
        ):

            bias, explanation = analyse_event(
                event
            )

            message = f"""
SAMIFOREX POST-NEWS ANALYSIS

Economic event:
{event_name}

Release time (Nigeria):
{nigeria_time(event_date)}

Actual:
{event.get("actual")}

Forecast:
{event.get("estimate")}

Previous:
{event.get("previous")}

ECONOMIC BIAS:
{bias}

MARKET INTERPRETATION:

{explanation}

MARKETS:

XAUUSD:
Use price action and DXY confirmation
before considering any direction.

BTCUSD:
Use price action and broader market
conditions for confirmation.

FINAL STATUS:
{bias}

No automatic trading is enabled.

This is an analytical alert,
not financial advice.
"""

            send_email(
                "SAMIFOREX: Economic News Released",
                message
            )

            history.append(post_id)

            save_history(history)

            print(
                "Post-news alert sent:",
                event_name
            )

    print("SAMIFOREX engine finished.")


# =====================================
# START
# =====================================

if __name__ == "__main__":

    try:
        run_engine()

    except Exception as error:

        print(
            "SAMIFOREX ERROR:",
            str(error)
        )

        raise
