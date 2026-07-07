import threading
import time
import requests
from datetime import datetime
from flask import Flask, jsonify, render_template, request

# ─── Configuration ───────────────────────────────────────
DEFAULT_THRESHOLD  = 30
WEATHER_UPDATE_MIN = 10
RAIN_BLOCK_PERCENT = 70
# ── No API key needed! Open-Meteo is completely free ─────

CROP_THRESHOLDS = {
    "tomato":     60, "potato":   55, "rice":       80,
    "corn":       50, "onion":    40, "cabbage":    65,
    "mustard":    45, "eggplant": 55, "spinach":    70,
    "strawberry": 65, "chili":    50, "watermelon": 45,
    "wheat":      55, "garlic":   40, "ginger":     60,
    "cucumber":   65, "lentil":   45, "sunflower":  50,
    "carrot":     55, "radish":   50, "pumpkin":    55,
    "bitter_gourd": 60, "bottle_gourd": 65, "beans": 55,
}

app = Flask(__name__)

_lock = threading.Lock()
sensor_data = {
    "raw": 0, "moisture": 0, "pump": "OFF",
    "timestamp": "Waiting for data…", "connected": False,
    "mode": "manual", "manual_pump": "OFF",   # power-on এ pump সবসময় OFF থাকবে
    "threshold": DEFAULT_THRESHOLD, "crop": "custom",
}

weather_data = {
    "temp":        "--",
    "humidity":    "--",
    "description": "Enter your location →",
    "rain_chance": 0,
    "rain_blocked": False,
    "icon":        "🌍",
    "last_update": "—",
    "city":        "",
    "lat":         None,
    "lon":         None,
    "error":       "",
}

location_state = {
    "city":    "",
    "lat":     None,
    "lon":     None,
    "pending": False,
}

# ── Weather code → description + icon ───────────────────
def parse_wmo(code):
    wmo = {
        0:  ("Clear Sky",        "☀️"),
        1:  ("Mainly Clear",     "🌤️"),
        2:  ("Partly Cloudy",    "⛅"),
        3:  ("Overcast",         "☁️"),
        45: ("Foggy",            "🌫️"),
        48: ("Icy Fog",          "🌫️"),
        51: ("Light Drizzle",    "🌦️"),
        53: ("Drizzle",          "🌧️"),
        55: ("Heavy Drizzle",    "🌧️"),
        61: ("Slight Rain",      "🌧️"),
        63: ("Rain",             "🌧️"),
        65: ("Heavy Rain",       "🌧️"),
        71: ("Slight Snow",      "❄️"),
        73: ("Snow",             "❄️"),
        75: ("Heavy Snow",       "❄️"),
        80: ("Rain Showers",     "🌦️"),
        81: ("Rain Showers",     "🌧️"),
        82: ("Heavy Showers",    "⛈️"),
        95: ("Thunderstorm",     "⛈️"),
        96: ("Thunderstorm+Hail","⛈️"),
        99: ("Heavy Thunderstorm","⛈️"),
    }
    return wmo.get(code, ("Unknown", "🌤️"))

# ── Fetch weather from Open-Meteo (no API key!) ──────────
def do_fetch_weather(lat, lon, city_name):
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,weather_code"
            f"&hourly=precipitation_probability"
            f"&forecast_days=1"
            f"&timezone=auto"
        )
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            d        = r.json()
            current  = d.get("current", {})
            temp     = round(current.get("temperature_2m", 0), 1)
            humidity = current.get("relative_humidity_2m", 0)
            wcode    = current.get("weather_code", 0)
            desc, icon = parse_wmo(wcode)

            # Max rain probability in next 6 hours
            hourly = d.get("hourly", {})
            probs  = hourly.get("precipitation_probability", [])
            rain_chance = round(max(probs[:6])) if probs else 0

            rain_blocked = rain_chance >= RAIN_BLOCK_PERCENT
            ts = datetime.now().strftime("%H:%M")

            with _lock:
                weather_data.update({
                    "temp":        temp,
                    "humidity":    humidity,
                    "description": desc,
                    "rain_chance": rain_chance,
                    "rain_blocked": rain_blocked,
                    "icon":        icon,
                    "last_update": ts,
                    "city":        city_name,
                    "lat":         lat,
                    "lon":         lon,
                    "error":       "",
                })
            print(f"[weather] {city_name} {desc} {temp}°C Rain:{rain_chance}%")
            return True
        else:
            with _lock:
                weather_data["error"] = f"Weather API error {r.status_code}"
    except Exception as e:
        with _lock:
            weather_data["error"] = str(e)
        print(f"[weather] Error: {e}")
    return False


def fetch_weather():
    while True:
        with _lock:
            lat     = location_state["lat"]
            lon     = location_state["lon"]
            city    = location_state["city"]
            pending = location_state["pending"]
            if pending:
                location_state["pending"] = False

        if lat is not None and lon is not None:
            do_fetch_weather(lat, lon, city)

        for _ in range(WEATHER_UPDATE_MIN * 60 // 5):
            time.sleep(5)
            with _lock:
                if location_state["pending"]:
                    break


def check_connection():
    last_ts = ""
    while True:
        time.sleep(15)
        with _lock:
            cur = sensor_data["timestamp"]
        if cur == last_ts and cur != "Waiting for data…":
            with _lock:
                sensor_data["connected"] = False
        last_ts = cur


# ── Routes ───────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html", crop_thresholds=CROP_THRESHOLDS)

@app.route("/data")
def data():
    with _lock:
        payload = dict(sensor_data)
        wd      = dict(weather_data)
    thr = payload["threshold"]
    payload["soil_status"] = (
        "Soil is Dry 🌵" if payload["moisture"] < thr else "Soil is Wet 💧"
    )
    payload["weather"] = wd
    return jsonify(payload)

@app.route("/sensor", methods=["POST"])
def sensor():
    body = request.get_json(force=True, silent=True)
    if not body:
        return jsonify({"status": "error"}), 400
    raw      = int(body.get("raw", 0))
    moisture = int(body.get("moisture", 0))
    ts       = datetime.now().strftime("%d %b %Y  %H:%M:%S")
    with _lock:
        thr          = sensor_data["threshold"]
        rain_blocked = weather_data["rain_blocked"]
        sensor_data["raw"]       = raw
        sensor_data["moisture"]  = moisture
        sensor_data["timestamp"] = ts
        sensor_data["connected"] = True
        if sensor_data["mode"] == "auto":
            sensor_data["pump"] = "OFF" if rain_blocked else ("ON" if moisture < thr else "OFF")
        else:
            sensor_data["pump"] = sensor_data["manual_pump"]
    return jsonify({"status": "ok"})

@app.route("/command")
def command():
    with _lock:
        mode         = sensor_data["mode"]
        moisture     = sensor_data["moisture"]
        manual       = sensor_data["manual_pump"]
        thr          = sensor_data["threshold"]
        rain_blocked = weather_data["rain_blocked"]
    if mode == "auto":
        cmd = "PUMP:OFF" if rain_blocked else ("PUMP:ON" if moisture < thr else "PUMP:OFF")
    else:
        cmd = f"PUMP:{manual}"
    return cmd, 200, {"Content-Type": "text/plain"}

@app.route("/set_mode", methods=["POST"])
def set_mode():
    body = request.get_json()
    mode = body.get("mode", "auto")
    with _lock:
        sensor_data["mode"] = mode
        if mode == "manual":
            sensor_data["manual_pump"] = "OFF"
            sensor_data["pump"]        = "OFF"
    return jsonify({"status": "ok", "mode": mode})

@app.route("/set_pump", methods=["POST"])
def set_pump():
    body  = request.get_json()
    state = body.get("pump", "OFF").upper()
    if state not in ("ON", "OFF"):
        return jsonify({"status": "error"}), 400
    with _lock:
        if sensor_data["mode"] == "manual":
            sensor_data["manual_pump"] = state
            sensor_data["pump"]        = state
    return jsonify({"status": "ok", "pump": state})

@app.route("/set_crop", methods=["POST"])
def set_crop():
    body = request.get_json()
    crop = body.get("crop", "custom").lower().replace(" ", "_")
    thr  = int(body.get("threshold", DEFAULT_THRESHOLD))
    if crop in CROP_THRESHOLDS:
        thr = CROP_THRESHOLDS[crop]
    with _lock:
        sensor_data["crop"]      = crop
        sensor_data["threshold"] = thr
    return jsonify({"status": "ok", "crop": crop, "threshold": thr})

# ── City search using Open-Meteo Geocoding (no key needed!)
@app.route("/geo_search")
def geo_search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    try:
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=6&language=en&format=json"
        r   = requests.get(url, timeout=6)
        if r.status_code == 200:
            results = []
            for c in r.json().get("results", []):
                name    = c.get("name", "")
                state   = c.get("admin1", "")
                country = c.get("country", "")
                lat     = c.get("latitude")
                lon     = c.get("longitude")
                label   = f"{name}, {state}, {country}" if state else f"{name}, {country}"
                results.append({
                    "label":   label,
                    "city":    name,
                    "country": country,
                    "lat":     lat,
                    "lon":     lon,
                })
            return jsonify(results)
    except Exception as e:
        print(f"[geo_search] Error: {e}")
    return jsonify([])

# ── Reverse geocode using Open-Meteo (no key needed!)
@app.route("/geo_reverse")
def geo_reverse():
    try:
        lat = float(request.args.get("lat", 0))
        lon = float(request.args.get("lon", 0))
        # Open-Meteo reverse geocoding
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json&zoom=10"
        headers = {"User-Agent": "KrishiSahayak/1.0"}
        r = requests.get(url, timeout=8, headers=headers)
        if r.status_code == 200:
            addr    = r.json().get("address", {})
            # জেলা/শহর level name নেওয়া হচ্ছে
            city = (addr.get("city") or addr.get("town") or
                    addr.get("district") or addr.get("county") or
                    addr.get("state_district") or "")
            if city:
                # Open-Meteo দিয়ে lat/lon verify করি
                return jsonify({"status": "ok", "city": city, "lat": lat, "lon": lon})
    except Exception as e:
        print(f"[geo_reverse] Error: {e}")
    return jsonify({"status": "error", "city": ""})

# ── Set location by lat/lon directly (GPS থেকে)
@app.route("/set_location", methods=["POST"])
def set_location():
    body = request.get_json(force=True, silent=True)
    if not body:
        return jsonify({"status": "error"}), 400

    city = body.get("city", "").strip()
    lat  = body.get("lat")
    lon  = body.get("lon")

    # lat/lon directly দেওয়া হলে city search দরকার নেই
    if lat is not None and lon is not None:
        with _lock:
            location_state.update({"city": city or f"{lat:.2f},{lon:.2f}", "lat": float(lat), "lon": float(lon), "pending": True})
            weather_data.update({"description": "Loading…", "icon": "🌀", "error": "", "city": city or "Your Location"})
        return jsonify({"status": "ok", "city": city})

    # city name দিয়ে search করে lat/lon বের করি
    if not city:
        return jsonify({"status": "error", "msg": "City or coordinates required"}), 400
    try:
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json"
        r   = requests.get(url, timeout=6)
        if r.status_code == 200 and r.json().get("results"):
            c    = r.json()["results"][0]
            lat  = c["latitude"]
            lon  = c["longitude"]
            name = c.get("name", city)
            with _lock:
                location_state.update({"city": name, "lat": lat, "lon": lon, "pending": True})
                weather_data.update({"description": "Loading…", "icon": "🌀", "error": "", "city": name})
            return jsonify({"status": "ok", "city": name})
        else:
            with _lock:
                weather_data.update({"error": f"City not found: {city}", "description": "City not found ❌", "icon": "❓"})
            return jsonify({"status": "error", "msg": f"City not found: {city}"}), 404
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500

@app.route("/ping")
def ping():
    return "pong", 200

if __name__ == "__main__":
    threading.Thread(target=fetch_weather,    daemon=True).start()
    threading.Thread(target=check_connection, daemon=True).start()
    app.run(debug=False, host="0.0.0.0", port=5000)
