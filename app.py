import threading
import time
import requests
from datetime import datetime
from flask import Flask, jsonify, render_template, request

DEFAULT_THRESHOLD  = 30
WEATHER_UPDATE_MIN = 15
RAIN_BLOCK_PERCENT = 70

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
    "mode": "manual", "manual_pump": "OFF",
    "threshold": DEFAULT_THRESHOLD, "crop": "custom",
}

weather_data = {
    "temp": "--", "humidity": "--",
    "description": "Enter your location →",
    "rain_chance": 0, "rain_blocked": False,
    "icon": "🌍", "last_update": "—",
    "city": "", "lat": None, "lon": None, "error": "",
}

location_state = {"city": "", "lat": None, "lon": None}

# ── Weather code → icon ──────────────────────────────────
def wcode_icon(desc):
    d = desc.lower()
    if "thunder" in d: return "⛈️"
    if "rain" in d or "drizzle" in d: return "🌧️"
    if "snow" in d: return "❄️"
    if "fog" in d or "mist" in d: return "🌫️"
    if "cloud" in d or "overcast" in d: return "☁️"
    if "clear" in d or "sunny" in d: return "☀️"
    if "partly" in d: return "⛅"
    return "🌤️"

# ── Fetch weather using wttr.in (no API key, no rate limit) ──
def do_fetch_weather(lat, lon, city_name):
    try:
        # wttr.in supports lat,lon directly
        url = f"https://wttr.in/{lat},{lon}?format=j1"
        r   = requests.get(url, timeout=20,
                           headers={"User-Agent": "KrishiSahayak/2.0"})
        if r.status_code == 200:
            data     = r.json()
            current  = data["current_condition"][0]
            temp     = current.get("temp_C", "--")
            humidity = current.get("humidity", "--")
            desc     = current.get("weatherDesc", [{}])[0].get("value", "Unknown")
            icon     = wcode_icon(desc)

            # Rain chance from hourly (next 3 hours)
            weather_list = data.get("weather", [])
            rain_chance  = 0
            if weather_list:
                hourly = weather_list[0].get("hourly", [])
                if hourly:
                    chances = [int(h.get("chanceofrain", 0)) for h in hourly[:3]]
                    rain_chance = max(chances) if chances else 0

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
            print(f"[weather] ✅ {city_name} {desc} {temp}°C Rain:{rain_chance}%")
            return True
        else:
            with _lock:
                weather_data["error"]       = f"API error {r.status_code}"
                weather_data["description"] = "Weather unavailable"
            print(f"[weather] ❌ wttr.in status {r.status_code}")
    except Exception as e:
        with _lock:
            weather_data["error"]       = str(e)
            weather_data["description"] = "Connection error"
        print(f"[weather] ❌ {e}")
    return False

def weather_refresh_loop():
    while True:
        time.sleep(WEATHER_UPDATE_MIN * 60)
        with _lock:
            lat  = location_state["lat"]
            lon  = location_state["lon"]
            city = location_state["city"]
        if lat is not None:
            print(f"[weather] 🔄 Refreshing {city}")
            do_fetch_weather(lat, lon, city)

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
        sensor_data.update({
            "raw": raw, "moisture": moisture,
            "timestamp": ts, "connected": True,
        })
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

@app.route("/geo_search")
def geo_search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    try:
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=6&language=en&format=json"
        r   = requests.get(url, timeout=15)
        if r.status_code == 200:
            results = []
            for c in r.json().get("results", []):
                name    = c.get("name", "")
                state   = c.get("admin1", "")
                country = c.get("country", "")
                lat     = c.get("latitude")
                lon     = c.get("longitude")
                label   = f"{name}, {state}, {country}" if state else f"{name}, {country}"
                results.append({"label": label, "city": name,
                                 "country": country, "lat": lat, "lon": lon})
            return jsonify(results)
    except Exception as e:
        print(f"[geo_search] {e}")
    return jsonify([])

@app.route("/geo_reverse")
def geo_reverse():
    try:
        lat = float(request.args.get("lat", 0))
        lon = float(request.args.get("lon", 0))
        url = (f"https://nominatim.openstreetmap.org/reverse"
               f"?lat={lat}&lon={lon}&format=json&zoom=10")
        r   = requests.get(url, timeout=15,
                           headers={"User-Agent": "KrishiSahayak/2.0"})
        if r.status_code == 200:
            addr = r.json().get("address", {})
            city = (addr.get("city") or addr.get("town") or
                    addr.get("district") or addr.get("county") or
                    addr.get("state_district") or "")
            if city:
                return jsonify({"status": "ok", "city": city, "lat": lat, "lon": lon})
    except Exception as e:
        print(f"[geo_reverse] {e}")
    return jsonify({"status": "error", "city": ""})

@app.route("/set_location", methods=["POST"])
def set_location():
    body = request.get_json(force=True, silent=True)
    if not body:
        return jsonify({"status": "error"}), 400

    city = body.get("city", "").strip()
    lat  = body.get("lat")
    lon  = body.get("lon")

    if lat is not None and lon is not None:
        lat, lon = float(lat), float(lon)
        city = city or f"{lat:.2f},{lon:.2f}"
        with _lock:
            location_state.update({"city": city, "lat": lat, "lon": lon})
            weather_data.update({"description": "Loading…", "icon": "🌀",
                                  "error": "", "city": city})
        threading.Thread(target=do_fetch_weather,
                         args=(lat, lon, city), daemon=True).start()
        return jsonify({"status": "ok", "city": city})

    if not city:
        return jsonify({"status": "error", "msg": "City required"}), 400

    try:
        url = (f"https://geocoding-api.open-meteo.com/v1/search"
               f"?name={city}&count=1&language=en&format=json")
        r   = requests.get(url, timeout=15)
        if r.status_code == 200 and r.json().get("results"):
            c    = r.json()["results"][0]
            lat  = c["latitude"]
            lon  = c["longitude"]
            name = c.get("name", city)
            with _lock:
                location_state.update({"city": name, "lat": lat, "lon": lon})
                weather_data.update({"description": "Loading…", "icon": "🌀",
                                      "error": "", "city": name})
            threading.Thread(target=do_fetch_weather,
                             args=(lat, lon, name), daemon=True).start()
            return jsonify({"status": "ok", "city": name})
        else:
            with _lock:
                weather_data.update({"error": f"City not found: {city}",
                                      "description": "City not found ❌", "icon": "❓"})
            return jsonify({"status": "error", "msg": f"City not found: {city}"}), 404
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500

@app.route("/ping")
def ping():
    return "pong", 200

if __name__ == "__main__":
    threading.Thread(target=weather_refresh_loop, daemon=True).start()
    threading.Thread(target=check_connection,     daemon=True).start()
    app.run(debug=False, host="0.0.0.0", port=5000)
