/*const API = "http://127.0.0.1:8000"; */

const isLoginPage = window.location.pathname === "/";

/* Global fetch helper (keeps session active) */
function apiFetch(url, options = {}) {
    return fetch(API + url, {
        credentials: "include",
        ...options
    });
}

/* =========================
   LOGIN PAGE FUNCTIONS
========================= */


function showSignIn() {
  const signIn = document.getElementById("signInForm");
  const signUp = document.getElementById("signUpForm");

  if (!signIn || !signUp) return;

  signIn.classList.remove("hidden");
  signUp.classList.add("hidden");

  document.getElementById("tabSignIn").classList.add("active");
  document.getElementById("tabSignUp").classList.remove("active");
}

function showSignUp() {
  const signIn = document.getElementById("signInForm");
  const signUp = document.getElementById("signUpForm");

  if (!signIn || !signUp) return;

  signIn.classList.add("hidden");
  signUp.classList.remove("hidden");

  document.getElementById("tabSignIn").classList.remove("active");
  document.getElementById("tabSignUp").classList.add("active");
}

function signup() {
  const name   = document.getElementById("signupName").value.trim();
  const regNo  = document.getElementById("signupRegNo").value.trim();
  const email  = document.getElementById("signupEmail").value.trim();
  const pass   = document.getElementById("pass").value;
  const repass = document.getElementById("repass").value;

  if (!regNo) { alert("Register number is required."); return; }

  let regex = /^(?=.*[a-z])(?=.*[A-Z])(?=.*[\W_]).{6,}$/;
  if (!regex.test(pass)) { alert("Password does not meet requirements."); return; }
  if (pass !== repass)   { alert("Passwords do not match."); return; }

  apiFetch("/signup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, reg_no: regNo, email, password: pass })
  })
  .then(res => res.json())
  .then(data => { alert(data.message); showSignIn(); });
}

function login() {
  const emailField = document.getElementById("loginEmail");
  const passField = document.getElementById("loginPassword");
  const roleField = document.getElementById("loginRole");

  if (!emailField || !passField || !roleField) {
    alert("Login form not found.");
    return;
  }

  const email = emailField.value;
  const password = passField.value;
  const role = roleField.value;

  apiFetch("/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: email,
      password: password,
      role: role
    })
  })
  .then(res => res.json())
  .then(data => {
    if (data.user) {
      window.location.href = "/home";
    } else {
      alert(data.message || "Invalid credentials");
    }
  });
}


function logout() {
  if(!confirm("Are you sure you want to logout?")) return;
  apiFetch("/logout", { method: "POST" })
    .then(() => {
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
  const parts = window.location.pathname.split("/");
  const clubId = parts[parts.length - 1];

  apiFetch(`/api/club/${clubId}`)
    .then(res => res.json())
    .then(data => {

      const club = data.club;
      const events = data.events;

      document.getElementById("clubName").textContent = club.name;
      document.getElementById("clubCategory").textContent = club.category;
      document.getElementById("clubDescription").textContent = club.description;

      renderEvents("clubEvents", events);
    });
}

function renderClubs(containerId, list) {

  const container = document.getElementById(containerId);
  if (!container) return;

  container.innerHTML = "";

  list.forEach(club => {

    const isFav = club.is_favorited ? "favorited" : "";
    const heart = club.is_favorited ? "❤️" : "🤍";

    container.innerHTML += `
      <div class="card">

        ${club.image ? `<img src="${API}/${club.image}" class="club-img">` : ""}

        <div class="card-top">
          <h3>${club.name}</h3>
          <span class="badge">${club.category}</span>
        </div>

        <small>${club.description}</small>

        <div class="event-actions">

          <a class="learn-link" href="/club/${club.id}">
            Learn More →
          </a>

          <button class="favorite-btn ${isFav}"
            onclick="toggleClubFavorite(${club.id}, this)">
            ${heart}
          </button>

        </div>

      </div>
    `;

  });

}

function filterClubs(category, element) {
  currentCategory = category;

  document.querySelectorAll(".filter")
    .forEach(btn => btn.classList.remove("active"));
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
    filtered = filtered.filter(c =>
      c.name.toLowerCase().includes(searchValue)
    );
  }

  renderClubs("clubGrid", filtered);
}

function searchClubs() {
  applyClubFilters();
}

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

  events.forEach(e => {

    const isFav = e.is_favorited ? "favorited" : "";
    const heart = e.is_favorited ? "❤️" : "🤍";

    container.innerHTML += `
      <div class="event-card">

        <div class="event-header">
          <h3>${e.title}</h3>
          <span class="domain-badge">${e.type}</span>
        </div>

        <p class="event-club">${e.club_name}</p>

        <div class="event-meta">
          <div>📅 ${e.date}</div>
          <div>⏰ ${e.time}</div>
          <div>📍 ${e.location}</div>
        </div>

        <div class="event-countdown" id="countdown-${e.id}">
          ⏳ Loading...
        </div>

        <div class="event-analytics">

          <div class="progress-bar">
            <div class="progress-fill"
              style="width:${((e.registered_count || 0) / (e.capacity || 1)) * 100}%">
            </div>
          </div>

          <span>
            👥 ${e.registered_count || 0} / ${e.capacity || 0}
          </span>

        </div>

        <div class="event-actions">

          <a href="/event/${e.id}" class="learn-link">
            View Event →
          </a>

          <button class="favorite-btn ${isFav}"
            onclick="toggleEventFavorite(${e.id}, this)">
            ${heart}
          </button>

        </div>

      </div>
    `;

    startCountdown(e.id, e.date, e.time);

  });

}

function startCountdown(eventId, date, time){

    const element = document.getElementById(`countdown-${eventId}`);
    if(!element) return;

    const eventDate = new Date(`${date} ${time}`);

    function update(){

        const now = new Date();
        const diff = eventDate - now;

        if(diff <= 0){
            element.innerHTML = "🔴 Event Started";
            return;
        }

        const days = Math.floor(diff / (1000*60*60*24));
        const hours = Math.floor((diff / (1000*60*60)) % 24);
        const minutes = Math.floor((diff / (1000*60)) % 60);

        if(days > 0){
            element.innerHTML = `⏳ Starts in ${days}d ${hours}h`;
        }
        else if(hours > 0){
            element.innerHTML = `⏳ Starts in ${hours}h ${minutes}m`;
        }
        else{
            element.innerHTML = `⏳ Starts in ${minutes}m`;
        }

    }

    update();
    setInterval(update, 60000);

}

function searchEvents() {
  const search = document.getElementById("eventSearch");
  if (!search) return;

  const value = search.value.toLowerCase();

  const filtered = allEvents.filter(e =>
    e.title.toLowerCase().includes(value)
  );

  renderEvents("eventGrid", filtered);
}

function filterEvents(type, element) {
  const filters = document.querySelectorAll("#filters .filter");

  filters.forEach(f => f.classList.remove("active"));
  element.classList.add("active");

  if (type === "all") {
    renderEvents("eventGrid", allEvents);
    return;
  }

  const filtered = allEvents.filter(e => e.type === type);
  renderEvents("eventGrid", filtered);
}

function registerForEvent(eventId) {

  apiFetch("/api/register", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      event_id: eventId
    })
  })
  .then(res => res.json())
  .then(data => {
    alert(data.message);
  });
}

/* =========================
   MY REGISTRATIONS
========================= */

function loadMyRegistrations() {
  apiFetch("/api/my-registrations")
    .then(res => {
      if (!res.ok) return null;
      return res.json();
    })
    .then(events => {
      const container = document.getElementById("myEvents");
      if (!container || !events) return;

      container.innerHTML = "";

      if (events.length === 0) {
        container.innerHTML = "<p>No registrations yet.</p>";
        return;
      }

      events.forEach(e => {
        container.innerHTML += `
          <a href="/event/${e.id}" class="event-card">
            <div class="event-header">
              <h3>${e.title}</h3>
              <span class="domain-badge">${e.type}</span>
            </div>

            <p class="event-club">${e.club_name}</p>

            <div class="event-meta">
              <div>📅 ${e.date}</div>
              <div>⏰ ${e.time}</div>
              <div>📍 ${e.location}</div>
            </div>
          </a>
        `;
      });
    });
}

/* =========================
   DASHBOARD FUNCTIONS
========================= */

function loadDashboardButton(){

    apiFetch("/me")
    .then(res => res.json())
    .then(data => {

        if(!data || !data.user) return;

        const user = data.user;
        const container = document.getElementById("dashboardButtons");

        if(!container) return;

        container.innerHTML = "";

        /* ADMIN */
        if(user.role === "admin"){

            container.innerHTML =
            `<button class="primary-btn"
            onclick="location.href='/admin'">
            Admin Dashboard
            </button>`;

            return;
        }

        /* STUDENT */
        container.innerHTML +=
        `<button class="primary-btn"
        onclick="location.href='/dashboard'">
        Student Dashboard
        </button>`;

        /* CLUB MEMBER */
        if(data.clubs && data.clubs.length > 0){

            container.innerHTML +=
            `<button class="primary-btn"
            onclick="location.href='/club-dashboard'">
            Club Dashboard
            </button>`;
        }

    });

}

function loadStudentDashboard() {
    apiFetch("/api/my-registrations")
    .then(res => res.json())
    .then(events => {
        const container = document.getElementById("studentEvents");
        if (!container) return;

        container.innerHTML = "";

        if (!events || events.length === 0) {
            container.innerHTML = "<p>No registrations yet.</p>";
            return;
        }

        events.forEach(e => {
            container.innerHTML += `
                <div class="card">
                    <h3>${e.title}</h3>
                    <p>${e.club_name}</p>
                    <small>${e.date} | ${e.time}</small>
                </div>
            `;
        });
    });
}

/* =========================
   PAGE INITIALIZER
========================= */

document.addEventListener("DOMContentLoaded", () => {

    const path = window.location.pathname;

    if (path.includes("home")) {
        loadMyRegistrations();
        loadDashboardButton();
        loadFeaturedClubs();
        loadStats();
    }

    // exact /clubs page only — NOT /club/1
    if (path === "/clubs" || path.startsWith("/clubs?")) {
        loadClubs();
    }

    if (path === "/events" || path.startsWith("/events?")) {
        loadEvents();
    }

    // /club/ID — handled entirely by club.html inline script, do NOT call loadClubDetails()

    if (path.includes("/event/")) {
        // handled entirely by event.html inline script
    }

    if (path === "/dashboard") {
        loadStudentDashboard();
    }

    if (path.includes("/calendar")) {
        loadEvents();
    }

    if (path.includes("/club-dashboard")) {
        // handled entirely by club_dashboard.html inline script
    }

});

/* LOGIN BACKGROUND SLIDESHOW */
document.addEventListener("DOMContentLoaded", () => {
  const bg = document.getElementById("bg");
  if (!bg) return;

  const images = [
    "/static/images/bg1.jpg",
    "/static/images/bg2.jpg",
    "/static/images/bg3.jpg"
  ];

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
    .then(data => {
      const featured = data.slice(0, 6);
      renderClubs("featuredClubs", featured);
    });
}

function animateCount(element, target) {

    let start = 0;
    const duration = 800;
    const step = Math.ceil(target / (duration / 20));

    const interval = setInterval(() => {

        start += step;

        if (start >= target) {
            element.innerText = target;
            clearInterval(interval);
        } else {
            element.innerText = start;
        }

    }, 20);

}


function loadStats(){

    apiFetch("/api/stats")
    .then(res => res.json())
    .then(data => {

        const club = document.getElementById("clubCount");
        const event = document.getElementById("eventCount");
        const member = document.getElementById("memberCount");

        if(club) animateCount(club, data.clubs);
        if(event) animateCount(event, data.events);
        if(member) animateCount(member, data.members);

    });

}


/* Page fade in */

window.addEventListener("load", () => {
    if(!isLoginPage){
        document.body.classList.add("page-loaded");
    }
});

/* Page load animation */

window.addEventListener("DOMContentLoaded", () => {
    if(!isLoginPage){
        document.body.classList.add("page-visible");
    }
});


/* Smooth page navigation */

if(window.location.pathname !== "/"){
document.querySelectorAll("a").forEach(link => {

    link.addEventListener("click", function(e) {

        const url = this.getAttribute("href");

        if (!url || url.startsWith("#") || url.startsWith("javascript") || url.startsWith("mailto")) {
            return;
        }

        e.preventDefault();

        document.body.classList.remove("page-visible");
        document.body.classList.add("page-leave");

        setTimeout(() => {
            window.location.href = url;
        }, 300);

    });

});
}


document.addEventListener("DOMContentLoaded", () => {

    const loader = document.getElementById("page-loader");

    if (!loader) return;

    document.querySelectorAll("a").forEach(link => {

        link.addEventListener("click", function(e) {

            const url = this.getAttribute("href");

            if (!url || url.startsWith("#") || url.startsWith("javascript") || url.startsWith("mailto")) {
                return;
            }

            loader.style.width = "80%";

        });

    });

});


window.addEventListener("load", () => {

    const loader = document.getElementById("page-loader");

    if (!loader) return;

    loader.style.width = "100%";

    setTimeout(() => {
        loader.style.width = "0%";
    }, 200);

});


function loadUpcomingEvents(){

    apiFetch("/api/events")
    .then(res => res.json())
    .then(events => {

        const container = document.getElementById("upcomingEvents");
        if(!container) return;

        const today = new Date();
        today.setHours(0,0,0,0);

        const upcoming = events
            .filter(e => new Date(e.date) >= today)
            .slice(0,3);

        renderEvents("upcomingEvents", upcoming);

    });

}

function togglePassword(){

    const pass = document.getElementById("loginPassword");
    const eye = document.getElementById("toggleEye");

    if(pass.type === "password"){
        pass.type = "text";
        eye.classList.remove("fa-eye");
        eye.classList.add("fa-eye-slash");
    }else{
        pass.type = "password";
        eye.classList.remove("fa-eye-slash");
        eye.classList.add("fa-eye");
    }

}

function loadClubEvents(clubId){

    apiFetch("/api/club-events/" + clubId)
    .then(res => res.json())
    .then(events => {

        const container = document.getElementById("clubEvents");

        if(!container) return;

        container.innerHTML = "";

        events.forEach(e => {

            container.innerHTML += `

<div class="event-card">

<h4>${e.title}</h4>

<p class="event-date">
📅 ${e.date} | ⏰ ${e.time}
</p>

<div class="event-actions">

<button class="btn-edit"
onclick="editEvent(${e.id})">
Edit
</button>

<button class="btn-reg"
onclick="viewRegistrations(${e.id})">
Registrations
</button>

<button class="btn-coord"
onclick="assignCoordinator(${clubId},${e.id})">
Coordinator
</button>

</div>

<input type="file"
onchange="uploadGalleryImage(${e.id},this)">

</div>

`;

        });

    });

}

function loadPendingEvents(clubId , role){

apiFetch("/api/pending-events/"+clubId)
.then(res=>res.json())
.then(events=>{

const container = document.getElementById("pendingEvents");

if(!container) return;

container.innerHTML="";

if(events.length === 0){
container.innerHTML = "<p>No pending approvals</p>";
return;
}

events.forEach(e=>{

let presidentStatus = e.president_approved ? "Approved" : "Not approved";
let adminStatus = e.admin_approved ? "Approved" : "Not approved";

let buttons = "";

/* PRESIDENT ACTIONS */

if(e.status === "pending_president"){
  if(role === "president"){
buttons = `
<button class="approve-btn" onclick="approveEvent(${e.id})">
Approve
</button>

<button class="delete-btn" onclick="openRejectModal(${e.id})">
Reject
</button>
`;
  }else{
    buttons= `<span>Waiting for president approval</span>`;
  }
}

/* WAITING FOR ADMIN */

if(e.status === "pending_admin"){
buttons = `
<span class="status-wait">
Waiting for admin approval
</span>
`;
}

container.innerHTML += `
<div class="card">

<h3>${e.title}</h3>

<p>
📅 ${e.date} | ⏰ ${e.time}
</p>

<p>President: ${presidentStatus}</p>

<p>Admin: ${adminStatus}</p>

${buttons}

</div>
`;

});

})
.catch(err=>{
console.error("Pending events error:",err);
});

}

function rejectEvent(eventId){

apiFetch("/api/events/"+eventId+"/reject",{
method:"PUT"
})
.then(res=>res.json())
.then(data=>{
alert(data.message);
location.reload();
});

}

function approveEvent(eventId){

    apiFetch("/api/events/" + eventId + "/president-approve",{
        method:"PUT"
    })
    .then(res=>res.json())
    .then(data=>{
        alert(data.message);
        location.reload();
    });

}

function loadMyClubs(){

apiFetch("/api/my-clubs")
.then(res=>res.json())
.then(clubs=>{

const container = document.getElementById("myClubs");

if(!container) return;

container.innerHTML="";

clubs.forEach((club,index)=>{

if(index === 0){
activeClubId = club.id;
loadClubEvents(club.id);
loadPendingEvents(club.id, club.role);
}

container.innerHTML += `
<div class="card">

<h3>${club.name}</h3>

<p class="club-role">
Role: ${club.role}
</p>

</div>
`;

});

});

}

function openClubEvents(clubId){

apiFetch("/api/club-events/"+clubId)
.then(res=>res.json())
.then(events=>{

const container = document.getElementById("clubEvents");

container.innerHTML="";

events.forEach(e => {

container.innerHTML+=`

<div class="event-card">

<h4>${e.title}</h4>

<p class="event-date">
📅 ${e.date} | ⏰ ${e.time}
</p>

<div class="event-actions">

<button class="btn-edit" onclick="editEvent(${e.id})">
Edit
</button>

<button class="btn-reg" onclick="viewRegistrations(${e.id})">
Registrations
</button>

<button class="btn-coord"
onclick="assignCoordinator(${clubId},${e.id})">
Coordinator
</button>

</div>

<input type="file"
onchange="uploadGalleryImage(${e.id},this)">

</div>

`;

});

});

loadPendingEvents(clubId);

}

var activeClubId = null;

function createClubEvent(){

if(!activeClubId){
alert("No club selected");
return;
}

apiFetch("/api/events",{

method:"POST",
headers:{
"Content-Type":"application/json"
},

body:JSON.stringify({

club_id:activeClubId,
title:document.getElementById("clubEventTitle").value,
description:document.getElementById("clubEventDesc").value,
date:document.getElementById("clubEventDate").value,
time:document.getElementById("clubEventTime").value,
location:document.getElementById("clubEventLocation").value,
type:document.getElementById("clubEventType").value,
capacity:document.getElementById("clubEventCapacity").value

})

})
.then(res=>res.json())
.then(data=>{

alert(data.message);

openClubEvents(activeClubId);

});

}

function viewRegistrations(eventId){

apiFetch("/api/event-registrations/" + eventId)
.then(res => res.json())
.then(students => {

let text = "Registered Students\n\n";

students.forEach(s => {

text += `${s.name} | ${s.department || ""} | Year ${s.year || ""}\n`;

});

if(students.length === 0){
text = "No registrations yet";
}

alert(text);

});

}


function uploadGalleryImage(eventId,input){

const file=input.files[0];

if(!file) return;

const formData=new FormData();
formData.append("image",file);

apiFetch("/api/events/"+eventId+"/upload-image",{
method:"POST",
body:formData
})
.then(res=>res.json())
.then(data=>{
alert(data.message);
});

}

function assignCoordinator(clubId,eventId){

apiFetch("/api/club/"+clubId+"/members")
.then(res=>res.json())
.then(members=>{

let options="";

members.forEach(m=>{
options+=`${m.id} : ${m.name}\n`;
});

const userId = prompt(
"Enter member ID to assign as coordinator:\n\n"+options
);

if(!userId) return;

apiFetch("/api/events/"+eventId+"/add-coordinator",{

method:"POST",

headers:{
"Content-Type":"application/json"
},

body:JSON.stringify({
user_id:userId
})

})

.then(res=>res.json())
.then(data=>{
alert(data.message);
});

});

}

function forgotPassword(){

    const email = prompt("Enter your email");

    fetch(API + "/forgot-password",{
        method:"POST",
        headers:{
            "Content-Type":"application/json"
        },
        body:JSON.stringify({email})
    })
    .then(res=>res.json())
    .then(data=>alert(data.message));

}

function toggleClubFavorite(clubId, button){

const isFav = button.classList.contains("favorited");

fetch(API + "/api/clubs/" + clubId + "/favorite",{
method: isFav ? "DELETE" : "POST",
credentials:"include"
})
.then(res=>res.json())
.then(()=>{

if(isFav){

button.classList.remove("favorited");
button.innerHTML="🤍";

}else{

button.classList.add("favorited");
button.innerHTML="❤️";

}

});

}

function toggleEventFavorite(eventId, button){

const isFav = button.classList.contains("favorited");

fetch(API + "/api/events/" + eventId + "/favorite",{
method: isFav ? "DELETE" : "POST",
credentials:"include"
})
.then(res=>res.json())
.then(()=>{

if(isFav){

button.classList.remove("favorited");
button.innerHTML="🤍";

}else{

button.classList.add("favorited");
button.innerHTML="❤️";

}

});

}

function submitFeedback(){

const parts = window.location.pathname.split("/");
const eventId = parts[parts.length-1];

const rating = document.getElementById("rating").value;
const comment = document.getElementById("feedbackComment").value;

apiFetch("/api/events/"+eventId+"/feedback",{

method:"POST",

headers:{
"Content-Type":"application/json"
},

body:JSON.stringify({
rating:rating,
comment:comment
})

})
.then(res=>res.json())
.then(data=>{

alert(data.message);

loadFeedback();

});

}

function loadFeedback(){

const parts = window.location.pathname.split("/");
const eventId = parts[parts.length-1];

apiFetch("/api/events/"+eventId+"/feedback")
.then(res=>res.json())
.then(list=>{

const container = document.getElementById("feedbackList");

if(!container) return;

container.innerHTML="";

list.forEach(f=>{

container.innerHTML+=`

<div class="card">

<h4>${f.name}</h4>

<p>Rating: ${"⭐".repeat(f.rating)}</p>

<p>${f.comment || ""}</p>

</div>

`;

});

});

}

function closeEditModal(){
    document.getElementById("editModal").style.display="none";
}

var rejectingEventId = null;

function openRejectModal(id){

rejectingEventId = id;

document.getElementById("rejectReason").value = "";

document.getElementById("rejectModal").style.display = "flex";

}

function closeRejectModal(){

document.getElementById("rejectModal").style.display = "none";

}

function submitReject(){

const reason = document.getElementById("rejectReason").value;

if(!reason){
alert("Please enter rejection reason");
return;
}

fetch("/api/events/" + rejectingEventId + "/reject",{

method:"PUT",
credentials:"include",

headers:{
"Content-Type":"application/json"
},

body: JSON.stringify({
reason: reason
})

})
.then(res=>res.json())
.then(data=>{

alert(data.message);

closeRejectModal();

loadPendingEvents();

});

}


/* =========================
   PROFILE DROPDOWN NAV
========================= */

function initProfileDropdown() {
    apiFetch("/me").then(r => r.json()).then(function(data) {
        if (!data || !data.user) return;
        var u = data.user;
        var wrap = document.getElementById("profileBtnWrap");
        if (!wrap) return;

        var initLetter = (u.name || "?").charAt(0).toUpperCase();
        var avatarSmall = u.profile_pic
            ? '<img class="p-avatar" src="' + API + '/' + u.profile_pic + '" alt="">'
            : '<span class="p-avatar-init">' + initLetter + '</span>';
        var avatarLarge = u.profile_pic
            ? '<img class="pd-avatar-lg" src="' + API + '/' + u.profile_pic + '" alt="">'
            : '<div class="pd-avatar-init-lg">' + initLetter + '</div>';

        var roleLabel = (u.role || "").charAt(0).toUpperCase() + (u.role || "").slice(1);

        var deptYearRow = (u.department || u.year)
            ? '<div class="pd-meta-row"><span>Dept / Year</span><span>'
              + (u.department || "—") + (u.year ? " · Yr " + u.year : "") + '</span></div>'
            : "";
        var regRow = u.reg_no
            ? '<div class="pd-meta-row"><span>Reg No</span><span>' + u.reg_no + '</span></div>'
            : "";

        var dashLink = u.role === "admin"
            ? '/admin'
            : '/dashboard';

        wrap.innerHTML =
            '<button class="profile-trigger" id="profileTrigger" onclick="toggleProfileDropdown(event)">'
            + avatarSmall
            + '<span class="p-name">' + u.name + '</span>'
            + '<span class="p-chevron">▼</span>'
            + '</button>'
            + '<div class="profile-dropdown" id="profileDropdown">'
            +   '<div class="pd-header">'
            +     avatarLarge
            +     '<div class="pd-info">'
            +       '<div class="pd-name">' + u.name + '</div>'
            +       '<div class="pd-email">' + u.email + '</div>'
            +       '<span class="pd-role">' + roleLabel + '</span>'
            +     '</div>'
            +   '</div>'
            +   (regRow || deptYearRow
                    ? '<div class="pd-meta">' + regRow + deptYearRow + '</div>'
                    : '')
            +   '<div class="pd-actions">'
            +     '<a href="' + dashLink + '" class="pd-action-btn">'
            +       '<span class="pd-ico">🏠</span> Dashboard'
            +     '</a>'
            +     '<a href="/dashboard#profile" class="pd-action-btn">'
            +       '<span class="pd-ico">👤</span> My Profile'
            +     '</a>'
            +     '<button class="pd-action-btn signout" onclick="logoutFromDropdown()">'
            +       '<span class="pd-ico">🚪</span> Sign Out'
            +     '</button>'
            +   '</div>'
            + '</div>';
    });
}

function toggleProfileDropdown(e) {
    e.stopPropagation();
    var wrap = document.getElementById("profileBtnWrap");
    if (wrap) wrap.classList.toggle("open");
}

function logoutFromDropdown() {
    if (!confirm("Are you sure you want to sign out?")) return;
    apiFetch("/logout", { method: "POST" }).then(function() {
        window.location.href = "/";
    });
}

// Close dropdown when clicking outside
document.addEventListener("click", function(e) {
    var wrap = document.getElementById("profileBtnWrap");
    if (wrap && !wrap.contains(e.target)) wrap.classList.remove("open");
});