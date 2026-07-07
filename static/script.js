/* Krishi-Sahayak – script.js */
const ARC_LEN = 251;

const els = {
  connDot:     document.getElementById("connDot"),
  connLabel:   document.getElementById("connLabel"),
  timestamp:   document.getElementById("timestamp"),
  moistureVal: document.getElementById("moistureVal"),
  gaugeArc:    document.getElementById("gaugeArc"),
  needle:      document.getElementById("needle"),
  thrMarker:   document.getElementById("thrMarker"),
  soilStatus:  document.getElementById("soilStatus"),
  pumpRing:    document.getElementById("pumpRing"),
  pumpState:   document.getElementById("pumpState"),
  pumpReason:  document.getElementById("pumpReason"),
  rawVal:      document.getElementById("rawVal"),
  rawBar:      document.getElementById("rawBar"),
  thrDryVal:   document.getElementById("thrDryVal"),
  thrWetVal:   document.getElementById("thrWetVal"),
  cropThresholdVal: document.getElementById("cropThresholdVal"),
  cropHint:    document.getElementById("cropHint"),
  wIcon:       document.getElementById("wIcon"),
  wCity:       document.getElementById("wCity"),
  wDesc:       document.getElementById("wDesc"),
  wTemp:       document.getElementById("wTemp"),
  wHumidity:   document.getElementById("wHumidity"),
  wRain:       document.getElementById("wRain"),
  rainAlert:   document.getElementById("rainAlert"),
  weatherBar:  document.getElementById("weatherBar"),
  wError:      document.getElementById("wError"),
};

let currentMode      = "auto";
let currentThreshold = 30;
let currentCrop      = "custom";

// ── Location Input + Autocomplete + GPS ───────────────────
let locTimer    = null;
let locSelected = -1;

function onLocationInput() {
  const q = document.getElementById("locationInput").value.trim();
  clearTimeout(locTimer);
  if (q.length < 2) { closeLoc(); return; }
  showLocLoading();
  locTimer = setTimeout(() => fetchCitySuggestions(q), 350);
}

function onLocationKey(e) {
  const dd    = document.getElementById("locDropdown");
  const items = dd.querySelectorAll(".loc-option:not(.loading)");
  if (e.key === "ArrowDown") {
    e.preventDefault();
    locSelected = Math.min(locSelected + 1, items.length - 1);
    highlightLoc(items);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    locSelected = Math.max(locSelected - 1, 0);
    highlightLoc(items);
  } else if (e.key === "Enter") {
    e.preventDefault();
    if (locSelected >= 0 && items[locSelected]) items[locSelected].click();
    else submitLocation();
  } else if (e.key === "Escape") {
    closeLoc();
  }
}

function highlightLoc(items) {
  items.forEach((el, i) => el.classList.toggle("active", i === locSelected));
  if (items[locSelected]) items[locSelected].scrollIntoView({block:"nearest"});
}

function showLocLoading() {
  const dd = document.getElementById("locDropdown");
  dd.innerHTML = '<div class="loc-option loading">🔍 Searching…</div>';
  dd.classList.add("open");
}

function closeLoc() {
  const dd = document.getElementById("locDropdown");
  dd.classList.remove("open");
  dd.innerHTML = "";
  locSelected = -1;
}

async function fetchCitySuggestions(q) {
  try {
    const res  = await fetch("/geo_search?q=" + encodeURIComponent(q));
    const data = await res.json();
    const dd   = document.getElementById("locDropdown");
    dd.innerHTML = ""; locSelected = -1;
    if (!data.length) {
      dd.innerHTML = '<div class="loc-option loading">No cities found</div>';
      dd.classList.add("open"); return;
    }
    data.forEach(item => {
      const d = document.createElement("div");
      d.className = "loc-option";
      d.innerHTML = `<span class="loc-name">${item.label}</span>`;
      d.onclick = () => {
        document.getElementById("locationInput").value = item.label;
        closeLoc();
        doSetLocation(item.city, item.lat, item.lon);
      };
      dd.appendChild(d);
    });
    dd.classList.add("open");
  } catch { closeLoc(); }
}

document.addEventListener("click", e => {
  if (!e.target.closest(".loc-search-wrap")) closeLoc();
});

function submitLocation() {
  const input = document.getElementById("locationInput");
  const city  = input.value.trim().split(",")[0].trim();
  if (!city) { input.focus(); return; }
  closeLoc();
  doSetLocation(city, null, null);
}

function doSetLocation(city, lat, lon) {
  els.wDesc.textContent    = "Loading…";
  els.wIcon.textContent    = "🌀";
  els.wError.style.display = "none";
  const body = lat !== null ? { city, lat, lon } : { city };
  fetch("/set_location", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body)
  })
  .then(r => r.json())
  .then(d => { if (d.status === "ok") els.wCity.textContent = d.city; })
  .catch(() => { els.wDesc.textContent = "Connection error"; });
}

// ── 📍 GPS — Location permission সঠিকভাবে handle করা ──────
function useMyLocation() {
  const btn = document.querySelector(".loc-gps");

  // Browser geolocation support নেই
  if (!navigator.geolocation) {
    showLocError("❌ এই browser-এ GPS সাপোর্ট নেই।");
    return;
  }

  // আগে permission check করি (যদি browser support করে)
  if (navigator.permissions) {
    navigator.permissions.query({ name: "geolocation" }).then(result => {
      if (result.state === "denied") {
        // Permission denied — user কে বলো কোথায় চালু করতে হবে
        showLocError(
          "📍 Location permission বন্ধ আছে। " +
          "Phone-এর Settings → Apps → Browser → Permissions → Location চালু করুন।"
        );
        return;
      }
      // prompt বা granted — try করি
      requestGPS(btn);
    }).catch(() => {
      // permissions API কাজ না করলে সরাসরি try
      requestGPS(btn);
    });
  } else {
    requestGPS(btn);
  }
}

function requestGPS(btn) {
  btn.textContent = "📍 Detecting…";
  btn.classList.add("loading");
  els.wDesc.textContent    = "Detecting location…";
  els.wIcon.textContent    = "📍";
  els.wError.style.display = "none";

  navigator.geolocation.getCurrentPosition(
    pos => {
      const { latitude: lat, longitude: lon } = pos.coords;
      fetch(`/geo_reverse?lat=${lat}&lon=${lon}`)
        .then(r => r.json())
        .then(d => {
          btn.textContent = "📍 My Location";
          btn.classList.remove("loading");
          const city = (d.status === "ok" && d.city) ? d.city : "Your Location";
          document.getElementById("locationInput").value = city;
          doSetLocation(city, lat, lon);
        })
        .catch(() => {
          btn.textContent = "📍 My Location";
          btn.classList.remove("loading");
          doSetLocation("Your Location", lat, lon);
        });
    },
    err => {
      btn.textContent = "📍 My Location";
      btn.classList.remove("loading");

      // ── Error code অনুযায়ী বাংলায় message ──
      if (err.code === 1) {
        // PERMISSION_DENIED
        showLocError(
          "📍 Location বন্ধ আছে। চালু করুন:\n" +
          "Chrome: Address bar-এর 🔒 আইকন → Location → Allow\n" +
          "অথবা Phone Settings → Apps → Chrome → Permissions → Location → Allow"
        );
      } else if (err.code === 2) {
        showLocError("❌ Location পাওয়া যাচ্ছে না। একটু পরে আবার চেষ্টা করুন।");
      } else if (err.code === 3) {
        showLocError("⏱️ Location timeout হয়েছে। আবার চেষ্টা করুন।");
      } else {
        showLocError("❌ Location error হয়েছে।");
      }
    },
    { timeout: 12000, maximumAge: 60000, enableHighAccuracy: false }
  );
}

function showLocError(msg) {
  els.wError.textContent   = msg;
  els.wError.style.display = "block";
  els.wDesc.textContent    = "Location error";
  els.wIcon.textContent    = "❌";
}

// ── Crop Search ────────────────────────────────────────────
function buildDropdown(filter = "") {
  const dd = document.getElementById("cropDropdown");
  dd.innerHTML = "";
  const q = filter.toLowerCase();
  let count = 0;

  if (!q || "custom".includes(q)) {
    const d = document.createElement("div");
    d.className = "crop-option";
    d.innerHTML = `🎛️ Custom <span class="thr-badge">slider</span>`;
    d.onclick = () => selectCrop("custom", null);
    dd.appendChild(d);
    count++;
  }

  Object.entries(CROP_LABELS).forEach(([key, label]) => {
    if (!q || label.toLowerCase().includes(q) || key.includes(q)) {
      const d = document.createElement("div");
      d.className = "crop-option";
      const thr = CROP_THRESHOLDS[key] || 30;
      d.innerHTML = `${label} <span class="thr-badge">${thr}%</span>`;
      d.onclick = () => selectCrop(key, thr);
      dd.appendChild(d);
      count++;
    }
  });
  dd.classList.toggle("open", count > 0);
}

function filterCrops() {
  buildDropdown(document.getElementById("cropSearch").value);
}

function showDropdown() {
  buildDropdown(document.getElementById("cropSearch").value);
}

function selectCrop(key, thr) {
  currentCrop = key;
  document.getElementById("cropDropdown").classList.remove("open");

  if (key === "custom") {
    document.getElementById("cropSearch").value = "Custom";
    document.getElementById("customThreshold").classList.add("visible");
    els.cropHint.textContent = "Custom";
  } else {
    document.getElementById("cropSearch").value = CROP_LABELS[key] || key;
    document.getElementById("customThreshold").classList.remove("visible");
    els.cropHint.textContent = CROP_LABELS[key] || key;
    setCrop(key, thr);
  }
}

document.addEventListener("click", e => {
  if (!e.target.closest(".crop-search-wrap")) {
    document.getElementById("cropDropdown").classList.remove("open");
  }
});

function onSliderChange(val) {
  document.getElementById("thrDisplay").textContent = val + "%";
}

function applyCustomThreshold() {
  const val = parseInt(document.getElementById("thrSlider").value);
  setCrop("custom", val);
}

function setCrop(crop, threshold) {
  fetch("/set_crop", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ crop, threshold })
  });
  currentThreshold = threshold;
  updateThresholdUI(threshold);
}

function updateThresholdUI(thr) {
  els.cropThresholdVal.textContent = thr + "%";
  els.thrDryVal.textContent = thr;
  els.thrWetVal.textContent = thr;
  const deg = -90 + (thr / 100) * 180;
  els.thrMarker.style.transform = `rotate(${deg}deg)`;
}

// ── Mode Controls ──────────────────────────────────────────
function setMode(mode) {
  currentMode = mode;
  fetch("/set_mode", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({mode}) });
  document.getElementById("btnAuto").classList.toggle("active", mode === "auto");
  document.getElementById("btnManual").classList.toggle("active", mode === "manual");
  const mc = document.getElementById("manualControls");
  mode === "manual" ? mc.classList.add("visible") : mc.classList.remove("visible");
  if (mode === "manual") setPump("OFF");
}

function setPump(state) {
  fetch("/set_pump", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({pump:state}) });
  document.getElementById("pumpOn").classList.toggle("active-btn",  state === "ON");
  document.getElementById("pumpOff").classList.toggle("active-btn", state === "OFF");
}

// ── Gauge ──────────────────────────────────────────────────
function setGauge(pct) {
  els.gaugeArc.style.strokeDashoffset = ARC_LEN - (pct / 100) * ARC_LEN;
  let c = pct >= currentThreshold + 20 ? "var(--teal)" : pct >= currentThreshold ? "var(--amber)" : "var(--red)";
  els.gaugeArc.style.stroke = c;
  els.needle.style.transform = `rotate(${-90 + (pct/100)*180}deg)`;
}

function animateNumber(el, value, suffix="") {
  const h = value + suffix;
  if (el.dataset.last === h) return;
  el.dataset.last = h; el.innerHTML = h;
  el.classList.remove("flip"); void el.offsetWidth; el.classList.add("flip");
}

// ── Weather Render ─────────────────────────────────────────
function renderWeather(w) {
  if (!w) return;
  els.wIcon.textContent     = w.icon        || "🌍";
  els.wCity.textContent     = w.city        || "—";
  els.wDesc.textContent     = w.description || "—";
  els.wTemp.textContent     = (w.temp !== "--" && w.temp !== undefined) ? w.temp + "°C" : "—";
  els.wHumidity.textContent = (w.humidity !== "--" && w.humidity !== undefined) ? w.humidity + "%" : "—";
  els.wRain.textContent     = (w.rain_chance !== undefined) ? w.rain_chance + "%" : "—";

  if (w.error) {
    els.wError.textContent   = "❌ " + w.error;
    els.wError.style.display = "block";
  } else {
    els.wError.style.display = "none";
  }

  const blocked = w.rain_blocked;
  els.rainAlert.style.display = blocked ? "block" : "none";
  els.weatherBar.classList.toggle("rain-warning", blocked);
}

// ── Main Render ────────────────────────────────────────────
function render(d) {
  els.connDot.className     = d.connected ? "conn-indicator online" : "conn-indicator offline";
  els.connLabel.textContent = d.connected ? "Connected" : "Disconnected";
  els.timestamp.textContent = d.timestamp;

  if (d.threshold && d.threshold !== currentThreshold) {
    currentThreshold = d.threshold;
    updateThresholdUI(d.threshold);
  }

  const m = d.moisture ?? 0;
  setGauge(m);
  animateNumber(els.moistureVal, m, '<span class="gauge-unit">%</span>');
  els.soilStatus.textContent = d.soil_status || "";
  els.soilStatus.className   = "soil-status " + (m < currentThreshold ? "dry" : "wet");

  const isOn = d.pump === "ON";
  els.pumpRing.className  = "pump-ring "  + (isOn ? "on" : "off");
  els.pumpState.className = "pump-state " + (isOn ? "on" : "off");
  if (els.pumpState.dataset.last !== d.pump) {
    els.pumpState.dataset.last = d.pump;
    els.pumpState.textContent  = d.pump;
    els.pumpState.classList.remove("flip"); void els.pumpState.offsetWidth; els.pumpState.classList.add("flip");
  }

  if (d.weather && d.weather.rain_blocked && d.mode === "auto") {
    els.pumpReason.textContent = "⛈️ Rain expected — blocked";
    els.pumpReason.className   = "pump-reason rain";
  } else if (d.mode === "auto") {
    els.pumpReason.textContent = m < currentThreshold ? "🌵 Soil dry — watering" : "💧 Soil moist — resting";
    els.pumpReason.className   = "pump-reason";
  } else {
    els.pumpReason.textContent = "🖐 Manual control";
    els.pumpReason.className   = "pump-reason";
  }

  animateNumber(els.rawVal, d.raw ?? 0);
  els.rawBar.style.width = (((d.raw ?? 0) / 1023) * 100).toFixed(1) + "%";

  if (d.mode && d.mode !== currentMode) {
    currentMode = d.mode;
    document.getElementById("btnAuto").classList.toggle("active", d.mode === "auto");
    document.getElementById("btnManual").classList.toggle("active", d.mode === "manual");
    const mc = document.getElementById("manualControls");
    d.mode === "manual" ? mc.classList.add("visible") : mc.classList.remove("visible");
  }

  renderWeather(d.weather);
}

// ── Poll ───────────────────────────────────────────────────
async function fetchData() {
  try {
    const res = await fetch("/data");
    if (!res.ok) throw new Error();
    render(await res.json());
  } catch {
    els.connDot.className     = "conn-indicator offline";
    els.connLabel.textContent = "Server error";
  }
}

updateThresholdUI(30);
buildDropdown();
fetchData();
setInterval(fetchData, 2000);
