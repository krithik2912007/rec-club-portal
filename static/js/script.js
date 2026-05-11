const API = "";
// Fix blank page on browser back button (bfcache restore)
window.addEventListener('pageshow', function(event) {
    if (event.persisted) {
        window.location.reload();
    }
});

var isLoginPage = window.location.pathname === "/";

/* Global fetch helper (keeps session active) */
function getCookie(name) {
  const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
  return match ? decodeURIComponent(match[2]) : null;
}

function apiFetch(url, options = {}) {
  const headers = options.headers || {};
  const method = (options.method || 'GET').toUpperCase();
  if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
    headers['X-CSRFToken'] = getCookie('csrftoken');
  }
  return fetch(API + url, {
    credentials: 'include',
    ...options,
    headers,
  });
}

/* =========================
   LOGIN PAGE FUNCTIONS
========================= */

function showSignIn() {
  const signIn = document.getElementById("signInForm") || document.getElementById("fSignin");
  const signUp = document.getElementById("signUpForm") || document.getElementById("fSignup");
  if (!signIn || !signUp) return;
  signIn.classList.remove("hidden");
  signUp.classList.add("hidden");
  const tabIn  = document.getElementById("tabSignIn");
  const tabUp  = document.getElementById("tabSignUp");
  if (tabIn)  tabIn.classList.add("active");
  if (tabUp)  tabUp.classList.remove("active");
}

function showSignUp() {
  const signIn = document.getElementById("signInForm") || document.getElementById("fSignin");
  const signUp = document.getElementById("signUpForm") || document.getElementById("fSignup");
  if (!signIn || !signUp) return;
  signIn.classList.add("hidden");
  signUp.classList.remove("hidden");
  const tabIn  = document.getElementById("tabSignIn");
  const tabUp  = document.getElementById("tabSignUp");
  if (tabIn)  tabIn.classList.remove("active");
  if (tabUp)  tabUp.classList.add("active");
}

// Track OTP email for verification step
var _otpEmail = "";

function signup() {
  var name   = document.getElementById("signupName").value.trim();
  var regNo  = (document.getElementById("signupRegNo").value || "").trim().toUpperCase();
  var email  = (document.getElementById("signupEmail").value || "").trim().toLowerCase();
  var dept   = document.getElementById("signupDept") ? document.getElementById("signupDept").value : "";
  var year   = document.getElementById("signupYear") ? document.getElementById("signupYear").value : "";
  var pass   = document.getElementById("pass").value;
  var repass = document.getElementById("repass").value;

  if (!name || !regNo || !email || !pass) { alert("All fields are required."); return; }

  // Email format check
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { alert("Please enter a valid email address."); return; }

  var regex = /^(?=.*[a-z])(?=.*[A-Z])(?=.*[\W_]).{6,}$/;
  if (!regex.test(pass)) { alert("Password must have uppercase, lowercase, special character and be at least 6 chars."); return; }
  if (pass !== repass)   { alert("Passwords do not match."); return; }

  // Disable button during request
  var btn = document.querySelector("#fSignup .submit-btn") || document.querySelector(".mform .submit-btn");
  if (btn) { btn.textContent = "Sending OTP..."; btn.disabled = true; }

  apiFetch("/signup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name, reg_no: regNo, email: email, password: pass, department: dept, year: year })
  })
  .then(res => res.json())
  .then(data => {
    if (btn) { btn.textContent = "Create Account →"; btn.disabled = false; }
    if (data.step === "verify_otp") {
      _otpEmail = email;
      showOtpModal(email);
    } else {
      alert(data.message);
    }
  })
  .catch(() => {
    if (btn) { btn.textContent = "Create Account →"; btn.disabled = false; }
    alert("Network error. Please try again.");
  });
}

function showOtpModal(email) {
  var existing = document.getElementById("otpModal");
  if (existing) existing.remove();

  var modal = document.createElement("div");
  modal.id = "otpModal";
  modal.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:99999;display:flex;align-items:center;justify-content:center;";

  var box = document.createElement("div");
  box.style.cssText = "background:#fff;border-radius:20px;padding:36px 32px;width:360px;max-width:92vw;text-align:center;box-shadow:0 20px 60px rgba(0,0,0,.25);";
  box.innerHTML = [
    "<div style='font-size:2.5rem;margin-bottom:8px;'>📧</div>",
    "<h3 style='margin:0 0 6px;font-size:1.2rem;color:#1e1b4b;font-weight:700;'>Verify Your Email</h3>",
    "<p style='color:#6b7280;font-size:.85rem;margin:0 0 20px;'>We sent a 6-digit OTP to<br><strong style='color:#1e1b4b;'>" + email + "</strong></p>",
    "<input id='otpInput' type='text' inputmode='numeric' maxlength='6' placeholder='Enter 6-digit OTP'",
    "  style='width:100%;padding:14px;font-size:1.4rem;text-align:center;letter-spacing:.3em;border:2px solid #e5e7eb;border-radius:12px;outline:none;box-sizing:border-box;font-family:monospace;'>",
    "<div id='otpMsg' style='font-size:.82rem;margin:8px 0 0;min-height:20px;color:#ef4444;'></div>",
    "<button onclick='verifyOtp()'",
    "  style='width:100%;margin-top:14px;padding:14px;background:#4f46e5;color:#fff;border:none;border-radius:12px;font-size:1rem;font-weight:700;cursor:pointer;'>Verify &amp; Create Account</button>",
    "<div style='margin-top:16px;font-size:.82rem;color:#9ca3af;'>Did not receive it?",
    "  <button onclick='resendOtp()' style='background:none;border:none;color:#4f46e5;cursor:pointer;font-weight:600;font-size:.82rem;padding:0;'>Resend OTP</button></div>",
    "<div id='otpTimer' style='font-size:.76rem;color:#9ca3af;margin-top:6px;'></div>"
  ].join("\n");

  modal.appendChild(box);
  document.body.appendChild(modal);

  // Numbers only — attach via JS not inline oninput to avoid quoting issues
  var inp = document.getElementById("otpInput");
  if (inp) {
    inp.addEventListener("input", function(){ this.value = this.value.replace(/[^0-9]/g, ""); });
    inp.focus();
  }
  startOtpTimer(600);
}

var _otpTimerInterval = null;
function startOtpTimer(seconds) {
  clearInterval(_otpTimerInterval);
  function tick() {
    var el = document.getElementById("otpTimer");
    if (!el) { clearInterval(_otpTimerInterval); return; }
    if (seconds <= 0) {
      el.textContent = "OTP expired. Please sign up again.";
      el.style.color = "#ef4444";
      clearInterval(_otpTimerInterval);
      return;
    }
    var m = Math.floor(seconds / 60);
    var s = seconds % 60;
    el.textContent = "Expires in " + m + ":" + (s < 10 ? "0" : "") + s;
    seconds--;
  }
  tick();
  _otpTimerInterval = setInterval(tick, 1000);
}

function verifyOtp() {
  var otp   = (document.getElementById("otpInput").value || "").trim();
  var msgEl = document.getElementById("otpMsg");
  if (otp.length !== 6) {
    if (msgEl) { msgEl.style.color = "#ef4444"; msgEl.textContent = "Please enter the 6-digit OTP."; }
    return;
  }
  var verifyBtn = document.querySelector("#otpModal button");
  if (verifyBtn) { verifyBtn.textContent = "Verifying..."; verifyBtn.disabled = true; }

  apiFetch("/verify-otp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: _otpEmail, otp: otp })
  })
  .then(res => res.json())
  .then(data => {
    if (verifyBtn) { verifyBtn.textContent = "✅ Verify & Create Account"; verifyBtn.disabled = false; }
    if (data.success) {
      clearInterval(_otpTimerInterval);
      var modal = document.getElementById("otpModal");
      if (modal) modal.remove();
      alert("✅ Email verified! Your account is ready. Please sign in.");
      showSignIn();
    } else {
      if (msgEl) { msgEl.style.color = "#ef4444"; msgEl.textContent = data.message || "Invalid OTP. Try again."; }
    }
  })
  .catch(() => {
    if (verifyBtn) { verifyBtn.textContent = "✅ Verify & Create Account"; verifyBtn.disabled = false; }
    if (msgEl) { msgEl.style.color = "#ef4444"; msgEl.textContent = "Network error. Try again."; }
  });
}

function resendOtp() {
  var msgEl = document.getElementById("otpMsg");
  apiFetch("/resend-otp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: _otpEmail })
  })
  .then(res => res.json())
  .then(data => {
    if (msgEl) {
      msgEl.style.color = data.message.includes("sent") ? "#10b981" : "#ef4444";
      msgEl.textContent = data.message;
      if (data.message.includes("sent")) startOtpTimer(600);
      setTimeout(function(){ if (msgEl) msgEl.textContent = ""; }, 4000);
    }
  })
  .catch(() => { if (msgEl) { msgEl.style.color = "#ef4444"; msgEl.textContent = "Failed to resend."; } });
}

function login() {
  const emailField = document.getElementById("loginEmail");
  const passField  = document.getElementById("loginPassword");

  // FIX: loginRole field is optional — backend determines role from DB, not from this field
  if (!emailField || !passField) {
    alert("Login form not found.");
    return;
  }

  const email    = emailField.value.trim();
  const password = passField.value;

  if (!email || !password) {
    alert("Please enter your email and password.");
    return;
  }

  apiFetch("/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  })
  .then(res => res.json())
  .then(data => {
    if (data.user) {
      // FIX: Cache user + clubs in sessionStorage so dashboard buttons render
      // instantly on /home without waiting for a second /me round-trip
      sessionStorage.setItem("_cpUser",  JSON.stringify(data.user));
      sessionStorage.setItem("_cpClubs", JSON.stringify(data.clubs || []));
      window.location.href = "/home";
    } else {
      alert(data.message || "Invalid credentials");
    }
  })
  .catch(() => alert("Network error. Please try again."));
}

function logout() {
  if (!confirm("Are you sure you want to logout?")) return;
  apiFetch("/logout", { method: "POST" })
    .then(() => {
      sessionStorage.removeItem("_cpUser");
      sessionStorage.removeItem("_cpClubs");
      window.location.href = "/";
    });
}

/* =========================
   CLUBS PAGE FUNCTIONS
========================= */

let clubs = [];
let currentCategory = "all";

function loadClubs() {
  apiFetch("/api/clubs")
    .then(res => res.json())
    .then(data => {
      clubs = data;
      applyClubFilters();
    });
}

function loadClubDetails() {
  const parts  = window.location.pathname.split("/");
  const clubId = parts[parts.length - 1];
  apiFetch(`/api/club/${clubId}`)
    .then(res => res.json())
    .then(data => {
      const club   = data.club;
      const events = data.events;
      const el = id => document.getElementById(id);
      if (el("clubName"))        el("clubName").textContent        = club.name;
      if (el("clubCategory"))    el("clubCategory").textContent    = club.category;
      if (el("clubDescription")) el("clubDescription").textContent = club.description;
      renderEvents("clubEvents", events);
    });
}

function renderClubs(containerId, list) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = "";
  // Update count label
  const countEl = document.getElementById("clubCount");
  if (countEl) countEl.textContent = "Showing " + list.length + " club" + (list.length !== 1 ? "s" : "");
  list.forEach(club => {
    const isFav = club.is_favorited ? "favorited" : "";
    const heart = club.is_favorited ? "❤️" : "🤍";
    container.innerHTML += `
      <div class="card">
        ${club.image ? `<img src="${API}/${club.image}" class="club-img">` : ""}
        <div class="card-top">
          <h3>${club.name}</h3>
          <span class="badge">${club.category || ""}</span>
        </div>
        <small>${club.description || ""}</small>
        <div class="event-actions">
          <a class="learn-link" href="/club/${club.id}">Learn More →</a>
          <button class="favorite-btn ${isFav}" onclick="toggleClubFavorite(${club.id}, this)">${heart}</button>
        </div>
      </div>`;
  });
}

function filterClubs(category, element) {
  currentCategory = category;
  document.querySelectorAll(".filter").forEach(btn => btn.classList.remove("active"));
  element.classList.add("active");
  applyClubFilters();
}

function applyClubFilters() {
  const searchInput = document.getElementById("search");
  const searchValue = searchInput ? searchInput.value.toLowerCase() : "";
  let filtered = clubs;
  if (currentCategory !== "all") {
    filtered = filtered.filter(c => c.category === currentCategory);
  }
  if (searchValue) {
    filtered = filtered.filter(c => c.name.toLowerCase().includes(searchValue));
  }
  renderClubs("clubGrid", filtered);
}

function searchClubs() { applyClubFilters(); }

/* =========================
   EVENTS PAGE FUNCTIONS
========================= */

let allEvents = [];

function loadEvents() {
  apiFetch("/api/events")
    .then(res => res.json())
    .then(events => {
      allEvents = events;
      renderEvents("eventGrid", allEvents);
    });
}

function renderEvents(containerId, events) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = "";
  // Update count label
  const countEl = document.getElementById("eventCount");
  if (countEl) countEl.textContent = "Showing " + events.length + " event" + (events.length !== 1 ? "s" : "");
  events.forEach(e => {
    const isFav = e.is_favorited ? "favorited" : "";
    const heart = e.is_favorited ? "❤️" : "🤍";
    container.innerHTML += `
      <div class="event-card">
        <div class="event-header">
          <h3>${e.title}</h3>
          <span class="domain-badge">${e.type || ""}</span>
        </div>
        <p class="event-club">${e.club_name || ""}</p>
        <div class="event-meta">
          <div>📅 ${e.date}</div>
          <div>⏰ ${e.time}</div>
          <div>📍 ${e.location || "TBA"}</div>
        </div>
        <div class="event-countdown" id="countdown-${e.id}">⏳ Loading...</div>
        <div class="event-analytics">
          <div class="progress-bar">
            <div class="progress-fill" style="width:${Math.min(((e.registered_count||0)/(e.capacity||1))*100,100)}%"></div>
          </div>
          <span>👥 ${e.registered_count||0} / ${e.capacity||0}</span>
        </div>
        <div class="event-actions">
          <a href="/event/${e.id}" class="learn-link">View Event →</a>
          <button class="favorite-btn ${isFav}" onclick="toggleEventFavorite(${e.id}, this)">${heart}</button>
        </div>
      </div>`;
    startCountdown(e.id, e.date, e.time);
  });
}

function startCountdown(eventId, date, time) {
  const element = document.getElementById(`countdown-${eventId}`);
  if (!element) return;
  const eventDate = new Date(`${date}T${time}`);
  function update() {
    const now  = new Date();
    const diff = eventDate - now;
    if (diff <= 0) { element.innerHTML = "🔴 Event Started"; return; }
    const days    = Math.floor(diff / (1000*60*60*24));
    const hours   = Math.floor((diff / (1000*60*60)) % 24);
    const minutes = Math.floor((diff / (1000*60)) % 60);
    if (days > 0)        element.innerHTML = `⏳ Starts in ${days}d ${hours}h`;
    else if (hours > 0)  element.innerHTML = `⏳ Starts in ${hours}h ${minutes}m`;
    else                 element.innerHTML = `⏳ Starts in ${minutes}m`;
  }
  update();
  setInterval(update, 60000);
}

// Track active event filter state
var _evTypeFilter = "all";

function applyEventFilters() {
  const searchEl = document.getElementById("eventSearch");
  const q = searchEl ? searchEl.value.toLowerCase() : "";
  let filtered = allEvents;
  // Apply type filter
  if (_evTypeFilter !== "all") {
    filtered = filtered.filter(e => e.type === _evTypeFilter);
  }
  // Apply search
  if (q) {
    filtered = filtered.filter(e => e.title.toLowerCase().includes(q));
  }
  renderEvents("eventGrid", filtered);
}

function searchEvents() {
  applyEventFilters();
}

function filterEvents(type, element) {
  _evTypeFilter = type;
  document.querySelectorAll("#filters .filter").forEach(f => f.classList.remove("active"));
  element.classList.add("active");
  applyEventFilters();
}

function registerForEvent(eventId) {
  apiFetch("/api/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event_id: eventId })
  })
  .then(res => res.json())
  .then(data => alert(data.message));
}

/* =========================
   MY REGISTRATIONS
========================= */

function loadMyRegistrations() {
  apiFetch("/api/my-registrations")
    .then(res => { if (!res.ok) return null; return res.json(); })
    .then(events => {
      const container = document.getElementById("myEvents");
      if (!container || !events) return;
      container.innerHTML = "";
      if (events.length === 0) { container.innerHTML = "<p>No registrations yet.</p>"; return; }
      events.forEach(e => {
        container.innerHTML += `
          <a href="/event/${e.id}" class="event-card">
            <div class="event-header">
              <h3>${e.title}</h3>
              <span class="domain-badge">${e.type||""}</span>
            </div>
            <p class="event-club">${e.club_name||""}</p>
            <div class="event-meta">
              <div>📅 ${e.date}</div><div>⏰ ${e.time}</div><div>📍 ${e.location||"TBA"}</div>
            </div>
          </a>`;
      });
    });
}

/* =========================
   DASHBOARD BUTTONS
========================= */

function _renderDashboardButtons(user, userClubs) {
  const container = document.getElementById("dashboardButtons");
  if (!container) return;
  container.innerHTML = "";

  if (user.role === "admin") {
    container.innerHTML = `<button class="primary-btn" onclick="location.href='/admin'">Admin Dashboard</button>`;
    return;
  }

  container.innerHTML += `<button class="primary-btn" onclick="location.href='/dashboard'">Student Dashboard</button>`;

  if (userClubs && userClubs.length > 0) {
    container.innerHTML += `<button class="primary-btn" onclick="location.href='/club-dashboard'">Club Dashboard</button>`;
  }
}

function loadDashboardButton() {
  // Show cached buttons instantly if available (set during login)
  const cachedUser  = sessionStorage.getItem("_cpUser");
  const cachedClubs = sessionStorage.getItem("_cpClubs");
  if (cachedUser) {
    try {
      _renderDashboardButtons(JSON.parse(cachedUser), JSON.parse(cachedClubs || "[]"));
    } catch (e) {}
  }

  // Always verify with server — this is the source of truth
  apiFetch("/me")
    .then(res => {
      if (!res.ok) throw new Error("Not logged in");
      return res.json();
    })
    .then(data => {
      if (!data || !data.user) {
        sessionStorage.removeItem("_cpUser");
        sessionStorage.removeItem("_cpClubs");
        const c = document.getElementById("dashboardButtons");
        if (c) c.innerHTML = "";
        return;
      }
      // Refresh cache with latest server data
      sessionStorage.setItem("_cpUser",  JSON.stringify(data.user));
      sessionStorage.setItem("_cpClubs", JSON.stringify(data.clubs || []));
      _renderDashboardButtons(data.user, data.clubs || []);
    })
    .catch(err => {
      console.warn("loadDashboardButton: /me failed", err);
      // If no cache either, show nothing — user is not logged in
    });
}

function loadStudentDashboard() {
  apiFetch("/api/my-registrations")
    .then(res => res.json())
    .then(events => {
      const container = document.getElementById("studentEvents");
      if (!container) return;
      container.innerHTML = "";
      if (!events || events.length === 0) { container.innerHTML = "<p>No registrations yet.</p>"; return; }
      events.forEach(e => {
        container.innerHTML += `
          <div class="card">
            <h3>${e.title}</h3>
            <p>${e.club_name||""}</p>
            <small>${e.date} | ${e.time}</small>
          </div>`;
      });
    });
}

/* =========================
   PAGE INITIALIZER
   FIX: Removed duplicate loadDashboardButton() from here.
   home.html inline script calls it directly — having both caused
   a race condition that wiped the rendered buttons.
========================= */

document.addEventListener("DOMContentLoaded", () => {
  const path = window.location.pathname;

  if (path.includes("home")) {
    loadMyRegistrations();
    loadFeaturedClubs();
    loadStats();
    // loadDashboardButton() is called by home.html inline script — do NOT call here too
  }

  if (path === "/clubs" || path.startsWith("/clubs?")) { loadClubs(); }
  if (path === "/events" || path.startsWith("/events?")) { loadEvents(); }
  if (path === "/dashboard") { loadStudentDashboard(); }
  if (path.includes("/calendar")) { loadEvents(); }
});

/* LOGIN BACKGROUND SLIDESHOW */
document.addEventListener("DOMContentLoaded", () => {
  const bg = document.getElementById("bg");
  if (!bg) return;
  const images = ["/static/images/bg1.jpg", "/static/images/bg2.jpg", "/static/images/bg3.jpg"];
  let index = 0;
  bg.style.backgroundImage = `url(${images[index]})`;
  setInterval(() => {
    index = (index + 1) % images.length;
    bg.style.backgroundImage = `url(${images[index]})`;
  }, 4000);
});

function loadFeaturedClubs() {
  apiFetch("/api/clubs")
    .then(res => res.json())
    .then(data => renderClubs("featuredClubs", data.slice(0, 6)));
}

function animateCount(element, target) {
  let start = 0;
  const step = Math.ceil(target / 40);
  const interval = setInterval(() => {
    start += step;
    if (start >= target) { element.innerText = target; clearInterval(interval); }
    else { element.innerText = start; }
  }, 20);
}

function loadStats() {
  apiFetch("/api/stats")
    .then(res => res.json())
    .then(data => {
      const club   = document.getElementById("clubCount");
      const event  = document.getElementById("eventCount");
      const member = document.getElementById("memberCount");
      if (club)   animateCount(club,   data.clubs);
      if (event)  animateCount(event,  data.events);
      if (member) animateCount(member, data.members);
    });
}

/* Page fade in */
window.addEventListener("load", () => {
  if (!isLoginPage) document.body.classList.add("page-loaded");
});

window.addEventListener("DOMContentLoaded", () => {
  if (!isLoginPage) document.body.classList.add("page-visible");
});

/* Smooth page navigation */
if (window.location.pathname !== "/") {
  document.querySelectorAll("a").forEach(link => {
    link.addEventListener("click", function(e) {
      const url = this.getAttribute("href");
      if (!url || url.startsWith("#") || url.startsWith("javascript") || url.startsWith("mailto")) return;
      e.preventDefault();
      document.body.classList.remove("page-visible");
      document.body.classList.add("page-leave");
      setTimeout(() => { window.location.href = url; }, 300);
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const loader = document.getElementById("page-loader");
  if (!loader) return;
  document.querySelectorAll("a").forEach(link => {
    link.addEventListener("click", function() {
      const url = this.getAttribute("href");
      if (!url || url.startsWith("#") || url.startsWith("javascript") || url.startsWith("mailto")) return;
      loader.style.width = "80%";
    });
  });
});

window.addEventListener("load", () => {
  const loader = document.getElementById("page-loader");
  if (!loader) return;
  loader.style.width = "100%";
  setTimeout(() => { loader.style.width = "0%"; }, 200);
});

function loadUpcomingEvents() {
  apiFetch("/api/events")
    .then(res => res.json())
    .then(events => {
      const container = document.getElementById("upcomingEvents");
      if (!container) return;
      const today = new Date();
      today.setHours(0,0,0,0);
      renderEvents("upcomingEvents", events.filter(e => new Date(e.date) >= today).slice(0, 3));
    });
}

function togglePassword() {
  const pass = document.getElementById("loginPassword");
  const eye  = document.getElementById("toggleEye");
  if (!pass) return;
  if (pass.type === "password") {
    pass.type = "text";
    if (eye) { eye.classList.remove("fa-eye"); eye.classList.add("fa-eye-slash"); }
  } else {
    pass.type = "password";
    if (eye) { eye.classList.remove("fa-eye-slash"); eye.classList.add("fa-eye"); }
  }
}

function loadClubEvents(clubId) {
  apiFetch("/api/club-events/" + clubId)
    .then(res => res.json())
    .then(events => {
      const container = document.getElementById("clubEvents");
      if (!container) return;
      container.innerHTML = "";
      events.forEach(e => {
        container.innerHTML += `
          <div class="event-card">
            <h4>${e.title}</h4>
            <p class="event-date">📅 ${e.date} | ⏰ ${e.time}</p>
            <div class="event-actions">
              <button class="btn-edit" onclick="editEvent(${e.id})">Edit</button>
              <button class="btn-reg"  onclick="viewRegistrations(${e.id})">Registrations</button>
              <button class="btn-coord" onclick="assignCoordinator(${clubId},${e.id})">Coordinator</button>
            </div>
            <input type="file" onchange="uploadGalleryImage(${e.id},this)">
          </div>`;
      });
    });
}

function loadPendingEvents(clubId, role) {
  apiFetch("/api/pending-events/" + clubId)
    .then(res => res.json())
    .then(events => {
      const container = document.getElementById("pendingEvents");
      if (!container) return;
      container.innerHTML = "";
      if (events.length === 0) { container.innerHTML = "<p>No pending approvals</p>"; return; }
      events.forEach(e => {
        let presidentStatus = e.president_approved ? "✅ Approved" : "⏳ Not approved";
        let adminStatus     = e.admin_approved     ? "✅ Approved" : "⏳ Not approved";
        let buttons = "";
        if (e.status === "pending_president") {
          if (role === "president") {
            buttons = `
              <button class="approve-btn" onclick="approveEvent(${e.id})">Approve</button>
              <button class="delete-btn"  onclick="openRejectModal(${e.id})">Reject</button>`;
          } else {
            buttons = `<span>Waiting for president approval</span>`;
          }
        }
        if (e.status === "pending_admin") {
          buttons = `<span class="status-wait">Waiting for admin approval</span>`;
        }
        container.innerHTML += `
          <div class="card">
            <h3>${e.title}</h3>
            <p>📅 ${e.date} | ⏰ ${e.time}</p>
            <p>President: ${presidentStatus}</p>
            <p>Admin: ${adminStatus}</p>
            ${buttons}
          </div>`;
      });
    })
    .catch(err => console.error("Pending events error:", err));
}

function rejectEvent(eventId) {
  apiFetch("/api/events/" + eventId + "/reject", { method: "PUT" })
    .then(res => res.json())
    .then(data => { alert(data.message); location.reload(); });
}

function approveEvent(eventId) {
  apiFetch("/api/events/" + eventId + "/president-approve", { method: "PUT" })
    .then(res => res.json())
    .then(data => { alert(data.message); location.reload(); });
}

function openClubEvents(clubId) {
  apiFetch("/api/club-events/" + clubId)
    .then(res => res.json())
    .then(events => {
      const container = document.getElementById("clubEvents");
      if (!container) return;
      container.innerHTML = "";
      events.forEach(e => {
        container.innerHTML += `
          <div class="event-card">
            <h4>${e.title}</h4>
            <p class="event-date">📅 ${e.date} | ⏰ ${e.time}</p>
            <div class="event-actions">
              <button class="btn-edit"  onclick="editEvent(${e.id})">Edit</button>
              <button class="btn-reg"   onclick="viewRegistrations(${e.id})">Registrations</button>
              <button class="btn-coord" onclick="assignCoordinator(${clubId},${e.id})">Coordinator</button>
            </div>
            <input type="file" onchange="uploadGalleryImage(${e.id},this)">
          </div>`;
      });
    });
  loadPendingEvents(clubId);
}

function openRejectModal(id) {
  rejectingEventId = id;
  const el = document.getElementById("rejectReason");
  if (el) el.value = "";
  const modal = document.getElementById("rejectModal");
  if (modal) modal.style.display = "flex";
}

function closeRejectModal() {
  const modal = document.getElementById("rejectModal");
  if (modal) modal.style.display = "none";
}

var rejectingEventId = null;

function submitReject() {
  const reason = document.getElementById("rejectReason").value;
  if (!reason) { alert("Please enter rejection reason"); return; }
  apiFetch("/api/events/" + rejectingEventId + "/reject", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason })
  })
  .then(res => res.json())
  .then(data => { alert(data.message); closeRejectModal(); location.reload(); });
}

function loadMyClubs() {
  apiFetch("/api/my-clubs")
    .then(res => res.json())
    .then(clubs => {
      const container = document.getElementById("myClubs");
      if (!container) return;
      container.innerHTML = "";
      clubs.forEach((club, index) => {
        if (index === 0) {
          activeClubId = club.id;
          loadClubEvents(club.id);
          loadPendingEvents(club.id, club.role);
        }
        container.innerHTML += `
          <div class="card">
            <h3>${club.name}</h3>
            <p class="club-role">Role: ${club.role}</p>
          </div>`;
      });
    });
}

var activeClubId = null;

function createClubEvent() {
  if (!activeClubId) { alert("No club selected"); return; }
  apiFetch("/api/events/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      club_id:  activeClubId,
      title:    document.getElementById("clubEventTitle").value,
      description: document.getElementById("clubEventDesc").value,
      date:     document.getElementById("clubEventDate").value,
      time:     document.getElementById("clubEventTime").value,
      location: document.getElementById("clubEventLocation").value,
      type:     document.getElementById("clubEventType").value,
      capacity: document.getElementById("clubEventCapacity").value
    })
  })
  .then(res => res.json())
  .then(data => { alert(data.message); loadClubEvents(activeClubId); });
}

function viewRegistrations(eventId) {
  apiFetch("/api/event-registrations/" + eventId)
    .then(res => res.json())
    .then(students => {
      let text = "Registered Students\n\n";
      students.forEach(s => { text += `${s.name} | ${s.department||""} | Year ${s.year||""}\n`; });
      if (students.length === 0) text = "No registrations yet";
      alert(text);
    });
}

function uploadGalleryImage(eventId, input) {
  const file = input.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("image", file);
  apiFetch("/api/events/" + eventId + "/upload-image", { method: "POST", body: formData })
    .then(res => res.json())
    .then(data => alert(data.message));
}

function assignCoordinator(clubId, eventId) {
  apiFetch("/api/club/" + clubId + "/members")
    .then(res => res.json())
    .then(members => {
      let options = "";
      members.forEach(m => { options += `${m.id} : ${m.name}\n`; });
      const userId = prompt("Enter member ID to assign as coordinator:\n\n" + options);
      if (!userId) return;
      apiFetch("/api/events/" + eventId + "/add-coordinator", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId })
      })
      .then(res => res.json())
      .then(data => alert(data.message));
    });
}

function forgotPassword() {
  const email = prompt("Enter your email");
  if (!email) return;
  fetch(API + "/forgot-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email })
  })
  .then(res => res.json())
  .then(data => alert(data.message));
}

function toggleClubFavorite(clubId, button) {
  const isFav = button.classList.contains("favorited");
  fetch(API + "/api/clubs/" + clubId + "/favorite", {
    method: isFav ? "DELETE" : "POST",
    credentials: "include"
  })
  .then(res => res.json())
  .then(() => {
    if (isFav) { button.classList.remove("favorited"); button.innerHTML = "🤍"; }
    else        { button.classList.add("favorited");    button.innerHTML = "❤️"; }
  });
}

function toggleEventFavorite(eventId, button) {
  const isFav = button.classList.contains("favorited");
  fetch(API + "/api/events/" + eventId + "/favorite", {
    method: isFav ? "DELETE" : "POST",
    credentials: "include"
  })
  .then(res => res.json())
  .then(() => {
    if (isFav) { button.classList.remove("favorited"); button.innerHTML = "🤍"; }
    else        { button.classList.add("favorited");    button.innerHTML = "❤️"; }
  });
}

function submitFeedback() {
  const parts   = window.location.pathname.split("/");
  const eventId = parts[parts.length - 1];
  const rating  = document.getElementById("rating").value;
  const comment = document.getElementById("feedbackComment").value;
  apiFetch("/api/events/" + eventId + "/feedback/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rating, comment })
  })
  .then(res => res.json())
  .then(data => { alert(data.message); loadFeedback(); });
}

function loadFeedback() {
  const parts   = window.location.pathname.split("/");
  const eventId = parts[parts.length - 1];
  apiFetch("/api/events/" + eventId + "/feedback")
    .then(res => res.json())
    .then(list => {
      const container = document.getElementById("feedbackList");
      if (!container) return;
      container.innerHTML = "";
      list.forEach(f => {
        container.innerHTML += `
          <div class="card">
            <h4>${f.name}</h4>
            <p>Rating: ${"⭐".repeat(f.rating)}</p>
            <p>${f.comment || ""}</p>
          </div>`;
      });
    });
}

function closeEditModal() {
  const m = document.getElementById("editModal");
  if (m) m.style.display = "none";
}

/* =========================
   PROFILE DROPDOWN NAV
========================= */

function initProfileDropdown() {
  apiFetch("/me")
    .then(r => {
      if (!r.ok) throw new Error("Not logged in");
      return r.json();
    })
    .then(function(data) {
      if (!data || !data.user) return;
      var u    = data.user;
      var wrap = document.getElementById("profileBtnWrap");
      if (!wrap) return;

      var initLetter   = (u.name || "?").charAt(0).toUpperCase();
      var avatarSmall  = u.profile_pic
        ? `<img class="p-avatar" src="${API}/${u.profile_pic}" alt="">`
        : `<span class="p-avatar-init">${initLetter}</span>`;
      var avatarLarge  = u.profile_pic
        ? `<img class="pd-avatar-lg" src="${API}/${u.profile_pic}" alt="">`
        : `<div class="pd-avatar-init-lg">${initLetter}</div>`;

      var roleLabel   = (u.role||"").charAt(0).toUpperCase() + (u.role||"").slice(1);
      var deptYearRow = (u.department || u.year)
        ? `<div class="pd-meta-row"><span>Dept / Year</span><span>${u.department||"—"}${u.year?" · Yr "+u.year:""}</span></div>`
        : "";
      var regRow = u.reg_no
        ? `<div class="pd-meta-row"><span>Reg No</span><span>${u.reg_no}</span></div>`
        : "";
      var dashLink = u.role === "admin" ? "/admin" : "/dashboard";

      wrap.innerHTML =
        `<button class="profile-trigger" id="profileTrigger" onclick="toggleProfileDropdown(event)">
          ${avatarSmall}
          <span class="p-name">${u.name}</span>
          <span class="p-chevron">▼</span>
        </button>
        <div class="profile-dropdown" id="profileDropdown">
          <div class="pd-header">
            ${avatarLarge}
            <div class="pd-info">
              <div class="pd-name">${u.name}</div>
              <div class="pd-email">${u.email}</div>
              <span class="pd-role">${roleLabel}</span>
            </div>
          </div>
          ${(regRow||deptYearRow) ? `<div class="pd-meta">${regRow}${deptYearRow}</div>` : ""}
          <div class="pd-actions">
            <a href="${dashLink}" class="pd-action-btn"><span class="pd-ico">🏠</span> Dashboard</a>
            <a href="/dashboard#profile" class="pd-action-btn"><span class="pd-ico">👤</span> My Profile</a>
            <button class="pd-action-btn signout" onclick="logoutFromDropdown()"><span class="pd-ico">🚪</span> Sign Out</button>
          </div>
        </div>`;
    })
    .catch(err => console.warn("initProfileDropdown: /me failed", err));
}

function toggleProfileDropdown(e) {
  e.stopPropagation();
  var wrap = document.getElementById("profileBtnWrap");
  if (wrap) wrap.classList.toggle("open");
}

function logoutFromDropdown() {
  if (!confirm("Are you sure you want to sign out?")) return;
  apiFetch("/logout", { method: "POST" }).then(function() {
    sessionStorage.removeItem("_cpUser");
    sessionStorage.removeItem("_cpClubs");
    window.location.href = "/";
  });
}

document.addEventListener("click", function(e) {
  var wrap = document.getElementById("profileBtnWrap");
  if (wrap && !wrap.contains(e.target)) wrap.classList.remove("open");
});