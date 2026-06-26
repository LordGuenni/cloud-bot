let sessionId = null;
let speechAuth = null;
let speechAuthExpiresAt = 0;
const chat = document.getElementById("chat");
const form = document.getElementById("chat-form");
const input = document.getElementById("message");
const voiceBtn = document.getElementById("voice-btn");
const restartBtn = document.getElementById("restart-btn");
const submitBtn = form.querySelector('button[type="submit"]');

// Chat helpers
function addMessage(role, text) {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.textContent = text;
  chat.appendChild(el);
  chat.scrollTop = chat.scrollHeight;
}

function showTypingIndicator() {
  const el = document.createElement("div");
  el.className = "typing";
  el.id = "typing-indicator";
  el.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';
  chat.appendChild(el);
  chat.scrollTop = chat.scrollHeight;
  return el;
}

function setButtonsEnabled(enabled) {
  submitBtn.disabled = !enabled;
  voiceBtn.disabled = !enabled;
  if (restartBtn) restartBtn.disabled = !enabled;
}

async function getSpeechAuth() {
  const now = Date.now();
  if (speechAuth && now < speechAuthExpiresAt) {
    return speechAuth;
  }
  const response = await fetch("/api/speech/token");
  if (!response.ok) {
    throw new Error("Could not get Azure Speech token.");
  }
  speechAuth = await response.json();
  speechAuthExpiresAt = now + 8 * 60 * 1000;
  return speechAuth;
}

async function speak(text) {
  if (!window.SpeechSDK) return;
  try {
    const { token, region } = await getSpeechAuth();
    const speechConfig = SpeechSDK.SpeechConfig.fromAuthorizationToken(token, region);
    speechConfig.speechSynthesisLanguage = "de-DE";
    speechConfig.speechSynthesisVoiceName = "de-DE-KatjaNeural";

    const synthesizer = new SpeechSDK.SpeechSynthesizer(speechConfig);
    synthesizer.speakTextAsync(
      text,
      () => synthesizer.close(),
      () => synthesizer.close()
    );
  } catch {
    // Keep chat interaction functional even if speech output fails.
  }
}

async function startSession() {
  const cachedSessionId = localStorage.getItem("chat_session_id");
  const cachedHistory = localStorage.getItem("chat_history");

  if (cachedSessionId && cachedHistory) {
    sessionId = cachedSessionId;
    try {
      const history = JSON.parse(cachedHistory);
      chat.innerHTML = "";
      history.forEach(item => {
        const el = document.createElement("div");
        el.className = `msg ${item.role}`;
        el.textContent = item.text;
        chat.appendChild(el);
      });
      chat.scrollTop = chat.scrollHeight;
      return;
    } catch (e) {
      // Clear corrupted cache and start fresh
      localStorage.removeItem("chat_session_id");
      localStorage.removeItem("chat_history");
    }
  }

  const indicator = showTypingIndicator();
  try {
    const response = await fetch("/api/chat/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" }
    });
    const payload = await response.json();
    sessionId = payload.session_id;
    localStorage.setItem("chat_session_id", sessionId);
    indicator.remove();
    addMessage("bot", payload.reply);
    
    // Cache welcome message
    localStorage.setItem("chat_history", JSON.stringify([{ role: "bot", text: payload.reply }]));
    
    await speak(payload.reply);
  } catch (err) {
    indicator.remove();
    throw err;
  }
}

async function sendMessage(message) {
  addMessage("user", message);
  
  // Cache user message
  let history = [];
  try {
    history = JSON.parse(localStorage.getItem("chat_history")) || [];
  } catch (e) {
    history = [];
  }
  history.push({ role: "user", text: message });
  localStorage.setItem("chat_history", JSON.stringify(history));

  setButtonsEnabled(false);
  const indicator = showTypingIndicator();

  try {
    const response = await fetch("/api/chat/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message })
    });

    indicator.remove();
    setButtonsEnabled(true);

    if (!response.ok) {
      addMessage("bot", "Error while sending the message.");
      return;
    }

    const payload = await response.json();
    addMessage("bot", payload.reply);
    await speak(payload.reply);

    if (payload.completed) {
      // Clear cache on successful registration
      localStorage.removeItem("chat_session_id");
      localStorage.removeItem("chat_history");
    } else {
      // Cache bot response
      try {
        history = JSON.parse(localStorage.getItem("chat_history")) || [];
      } catch (e) {
        history = [];
      }
      history.push({ role: "bot", text: payload.reply });
      localStorage.setItem("chat_history", JSON.stringify(history));
    }
  } catch (err) {
    indicator.remove();
    setButtonsEnabled(true);
    addMessage("bot", "Network error.");
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  await sendMessage(message);
});

voiceBtn.addEventListener("click", async () => {
  if (!window.SpeechSDK) {
    addMessage("bot", "Azure Speech SDK is not available in this browser.");
    return;
  }

  voiceBtn.disabled = true;
  voiceBtn.textContent = "Listening...";
  try {
    const { token, region } = await getSpeechAuth();
    const speechConfig = SpeechSDK.SpeechConfig.fromAuthorizationToken(token, region);
    speechConfig.speechRecognitionLanguage = "de-DE";
    const audioConfig = SpeechSDK.AudioConfig.fromDefaultMicrophoneInput();
    const recognizer = new SpeechSDK.SpeechRecognizer(speechConfig, audioConfig);

    recognizer.recognizeOnceAsync(
      async (result) => {
        recognizer.close();
        if (result.reason === SpeechSDK.ResultReason.RecognizedSpeech) {
          const transcript = (result.text || "").trim();
          if (transcript) {
            await sendMessage(transcript);
          }
        } else {
          addMessage("bot", "Speech recognition did not return text.");
        }
        voiceBtn.disabled = false;
        voiceBtn.textContent = "🎤 Voice";
      },
      () => {
        recognizer.close();
        addMessage("bot", "Speech recognition failed. Try again.");
        voiceBtn.disabled = false;
        voiceBtn.textContent = "🎤 Voice";
      }
    );
  } catch {
    addMessage("bot", "Could not initialize Azure Speech recognition.");
    voiceBtn.disabled = false;
    voiceBtn.textContent = "🎤 Voice";
  }
});

if (restartBtn) {
  restartBtn.addEventListener("click", async () => {
    localStorage.removeItem("chat_session_id");
    localStorage.removeItem("chat_history");
    chat.innerHTML = "";
    sessionId = null;
    await startSession();
  });
}

// Initialize session on startup
startSession().catch(() => addMessage("bot", "Could not initialize chat session."));


// --- ADMIN DASHBOARD IMPLEMENTATION ---

const tabChat = document.getElementById("tab-chat");
const tabAdmin = document.getElementById("tab-admin");
const chatView = document.getElementById("chat-view");
const adminView = document.getElementById("admin-view");

let allAccounts = [];
let filteredAccounts = [];

let msalInstance = null;
let entraConfig = null;
let adminToken = null;

async function getEntraConfig() {
  if (entraConfig) return entraConfig;
  try {
    const response = await fetch("/api/admin/config");
    if (!response.ok) throw new Error("Could not load admin config");
    entraConfig = await response.json();
    return entraConfig;
  } catch (err) {
    console.error(err);
    return { client_id: "", tenant_id: "" };
  }
}

async function initMsal(clientId, tenantId) {
  if (msalInstance) return msalInstance;
  if (typeof msal === "undefined") {
    throw new Error("Microsoft MSAL SDK konnte nicht geladen werden. Bitte Internetverbindung oder Adblocker prüfen.");
  }
  const msalConfig = {
    auth: {
      clientId: clientId,
      authority: `https://login.microsoftonline.com/${tenantId}`,
      redirectUri: window.location.origin
    },
    cache: {
      cacheLocation: "sessionStorage",
      storeAuthStateInCookie: false
    }
  };
  msalInstance = new msal.PublicClientApplication(msalConfig);
  if (typeof msalInstance.initialize === "function") {
    await msalInstance.initialize();
  }
  return msalInstance;
}

// Tab navigation handler
tabChat.addEventListener("click", () => {
  tabChat.classList.add("active");
  tabAdmin.classList.remove("active");
  chatView.classList.add("active");
  adminView.classList.remove("active");
});

tabAdmin.addEventListener("click", async () => {
  const config = await getEntraConfig();
  
  if (!config.client_id) {
    // Local / Offline fallback mode: Client ID not configured in key vault
    const success = await loadAccounts(null);
    if (success) {
      tabAdmin.classList.add("active");
      tabChat.classList.remove("active");
      adminView.classList.add("active");
      chatView.classList.remove("active");
    }
    return;
  }
  
  try {
    const pca = await initMsal(config.client_id, config.tenant_id);
    
    // Check if user is already signed in
    const accounts = pca.getAllAccounts();
    let tokenResponse = null;
    
    if (accounts.length > 0) {
      try {
        tokenResponse = await pca.acquireTokenSilent({
          scopes: ["User.Read"],
          account: accounts[0]
        });
      } catch (err) {
        // silent acquisition failed
      }
    }
    
    if (!tokenResponse) {
      tokenResponse = await pca.loginPopup({
        scopes: ["User.Read"],
        prompt: "select_account"
      });
    }
    
    adminToken = tokenResponse.idToken;
    const success = await loadAccounts(adminToken);
    if (success) {
      tabAdmin.classList.add("active");
      tabChat.classList.remove("active");
      adminView.classList.add("active");
      chatView.classList.remove("active");
    } else {
      adminToken = null;
    }
  } catch (err) {
    console.error("Authentication error:", err);
    alert("Entra ID Authentifizierung fehlgeschlagen: " + err.message);
  }
});

// Load account data from backend API
async function loadAccounts(token) {
  try {
    const headers = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const response = await fetch("/api/admin/accounts", { headers });
    
    if (response.status === 401) {
      alert("Zugriff verweigert (401 Unauthorized). Keine Berechtigung für das Admin-Dashboard.");
      return false;
    }
    if (!response.ok) throw new Error("Could not fetch accounts.");
    allAccounts = await response.json();
    filteredAccounts = [...allAccounts];
    
    // Clear search filter when switching back
    document.getElementById("admin-search").value = "";
    document.getElementById("clear-search").style.display = "none";
    
    renderDashboard();
    return true;
  } catch (err) {
    console.error(err);
    alert("Fehler beim Laden der Accounts: " + err.message);
    return false;
  }
}

// Render admin dashboard stats and accounts table
function renderDashboard() {
  calculateStats();
  renderTable();
}

function calculateStats() {
  const total = allAccounts.length;
  document.getElementById("stat-total").textContent = total;

  if (total === 0) {
    document.getElementById("stat-avg-age").textContent = "0 J.";
    document.getElementById("stat-phone-rate").textContent = "0%";
    document.getElementById("stat-top-country").textContent = "-";
    return;
  }

  let ageSum = 0;
  let validAges = 0;
  let phoneCount = 0;
  const countries = {};

  allAccounts.forEach(acc => {
    // Age calculation from DD.MM.YYYY or YYYY-MM-DD
    if (acc.birthdate) {
      const parts = acc.birthdate.split('.');
      let birthDate = null;
      if (parts.length === 3) {
        birthDate = new Date(parts[2], parts[1] - 1, parts[0]);
      } else {
        birthDate = new Date(acc.birthdate);
      }
      if (birthDate && !isNaN(birthDate)) {
        const age = Math.floor((new Date() - birthDate) / (365.25 * 24 * 60 * 60 * 1000));
        if (age >= 0 && age < 120) {
          ageSum += age;
          validAges++;
        }
      }
    }

    // Phone fill rate
    if (acc.phone && acc.phone.trim()) {
      phoneCount++;
    }

    // Country distribution
    if (acc.country) {
      const c = acc.country.trim();
      countries[c] = (countries[c] || 0) + 1;
    }
  });

  const avgAge = validAges > 0 ? Math.round(ageSum / validAges) : 0;
  document.getElementById("stat-avg-age").textContent = avgAge + " J.";

  const phoneRate = Math.round((phoneCount / total) * 100);
  document.getElementById("stat-phone-rate").textContent = phoneRate + "%";

  let topCountry = "-";
  let maxCount = 0;
  for (const [c, count] of Object.entries(countries)) {
    if (count > maxCount) {
      maxCount = count;
      topCountry = c;
    }
  }
  document.getElementById("stat-top-country").textContent = topCountry;
}

const listEl = document.getElementById("accounts-list");
const noAccountsEl = document.getElementById("no-accounts");
const tableEl = document.getElementById("accounts-table");

function renderTable() {
  listEl.innerHTML = "";
  if (filteredAccounts.length === 0) {
    tableEl.style.display = "none";
    noAccountsEl.style.display = "flex";
    return;
  }

  tableEl.style.display = "table";
  noAccountsEl.style.display = "none";

  filteredAccounts.forEach((acc, idx) => {
    const tr = document.createElement("tr");
    
    const name = `${acc.first_name || ""} ${acc.last_name || ""}`;
    const birthdate = acc.birthdate || "-";
    const email = acc.email || "-";
    const phone = acc.phone || "-";
    const location = `${acc.city || ""}${acc.city && acc.country ? ", " : ""}${acc.country || ""}` || "-";

    tr.innerHTML = `
      <td><strong>${escapeHtml(name)}</strong></td>
      <td>${escapeHtml(birthdate)}</td>
      <td><a href="mailto:${escapeHtml(email)}" style="color: #60a5fa; text-decoration: none;">${escapeHtml(email)}</a></td>
      <td>${escapeHtml(phone)}</td>
      <td>${escapeHtml(location)}</td>
      <td style="text-align: center;">
        <button class="btn-action" onclick="showDetails(${idx})">Details</button>
      </td>
    `;
    listEl.appendChild(tr);
  });
}

function escapeHtml(str) {
  if (!str) return "";
  return str.toString()
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Global modal details viewer
window.showDetails = function(idx) {
  const acc = filteredAccounts[idx];
  if (!acc) return;

  document.getElementById("detail-first-name").textContent = acc.first_name || "-";
  document.getElementById("detail-last-name").textContent = acc.last_name || "-";
  document.getElementById("detail-birthdate").textContent = acc.birthdate || "-";
  document.getElementById("detail-address").textContent = acc.address_line || "-";
  document.getElementById("detail-zip-city").textContent = `${acc.postal_code || ""} ${acc.city || ""}`.trim() || "-";
  document.getElementById("detail-country").textContent = acc.country || "-";
  document.getElementById("detail-email").textContent = acc.email || "-";
  document.getElementById("detail-phone").textContent = acc.phone || "-";

  document.getElementById("details-modal").style.display = "block";
};

// Modal close button controls
const modal = document.getElementById("details-modal");
const closeModalBtn = document.querySelector(".close-modal");

closeModalBtn.addEventListener("click", () => {
  modal.style.display = "none";
});

window.addEventListener("click", (event) => {
  if (event.target === modal) {
    modal.style.display = "none";
  }
});

// Search input functionality
const searchInput = document.getElementById("admin-search");
const clearSearchBtn = document.getElementById("clear-search");

searchInput.addEventListener("input", () => {
  const query = searchInput.value.toLowerCase().trim();
  if (query) {
    clearSearchBtn.style.display = "block";
  } else {
    clearSearchBtn.style.display = "none";
  }

  filteredAccounts = allAccounts.filter(acc => {
    const name = `${acc.first_name || ""} ${acc.last_name || ""}`.toLowerCase();
    const email = (acc.email || "").toLowerCase();
    const city = (acc.city || "").toLowerCase();
    const country = (acc.country || "").toLowerCase();
    const phone = (acc.phone || "").toLowerCase();
    const birthdate = (acc.birthdate || "").toLowerCase();
    
    return name.includes(query) || 
           email.includes(query) || 
           city.includes(query) || 
           country.includes(query) || 
           phone.includes(query) ||
           birthdate.includes(query);
  });

  renderTable();
});

clearSearchBtn.addEventListener("click", () => {
  searchInput.value = "";
  clearSearchBtn.style.display = "none";
  filteredAccounts = [...allAccounts];
  renderTable();
});

// Helper to get formatted timestamps for exported files
function getTimestamp() {
  const d = new Date();
  return d.getFullYear() +
    String(d.getMonth() + 1).padStart(2, '0') +
    String(d.getDate()).padStart(2, '0') + "_" +
    String(d.getHours()).padStart(2, '0') +
    String(d.getMinutes()).padStart(2, '0');
}

// JSON Data Export
document.getElementById("export-json").addEventListener("click", () => {
  if (filteredAccounts.length === 0) {
    alert("Keine Daten zum Exportieren vorhanden.");
    return;
  }
  const jsonString = JSON.stringify(filteredAccounts, null, 2);
  const blob = new Blob([jsonString], { type: "application/json;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  
  const link = document.createElement("a");
  link.setAttribute("href", url);
  link.setAttribute("download", `azure_registrations_${getTimestamp()}.json`);
  link.style.visibility = "hidden";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
});

// CSV Data Export
document.getElementById("export-csv").addEventListener("click", () => {
  if (filteredAccounts.length === 0) {
    alert("Keine Daten zum Exportieren vorhanden.");
    return;
  }
  
  const headers = ["Vorname", "Nachname", "Geburtsdatum", "E-Mail", "Telefon", "Strasse_Hausnummer", "PLZ", "Ort", "Land"];
  const rows = filteredAccounts.map(acc => [
    acc.first_name || "",
    acc.last_name || "",
    acc.birthdate || "",
    acc.email || "",
    acc.phone || "",
    acc.address_line || "",
    acc.postal_code || "",
    acc.city || "",
    acc.country || ""
  ]);

  // Convert to CSV with Excel-compatible UTF-8 BOM
  let csvContent = "\ufeff";
  csvContent += headers.map(h => `"${h.replace(/"/g, '""')}"`).join(",") + "\r\n";
  
  rows.forEach(row => {
    csvContent += row.map(v => `"${v.toString().replace(/"/g, '""')}"`).join(",") + "\r\n";
  });

  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  
  const link = document.createElement("a");
  link.setAttribute("href", url);
  link.setAttribute("download", `azure_registrations_${getTimestamp()}.csv`);
  link.style.visibility = "hidden";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
});

// PDF statistics and users table generation
document.getElementById("export-pdf").addEventListener("click", () => {
  if (filteredAccounts.length === 0) {
    alert("Keine Daten zum Generieren der PDF-Statistik vorhanden.");
    return;
  }

  const { jsPDF } = window.jspdf;
  const doc = new jsPDF();
  
  // Title Header
  doc.setFont("helvetica", "bold");
  doc.setFontSize(22);
  doc.setTextColor(37, 99, 235); // Matches var(--accent-primary)
  doc.text("THB Azure Registration Bot", 14, 22);
  
  doc.setFont("helvetica", "normal");
  doc.setFontSize(13);
  doc.setTextColor(100, 116, 139); // Matches var(--text-muted)
  doc.text("Systemstatistiken & Benutzeruebersicht", 14, 30);
  
  // Horizontal separator line
  doc.setDrawColor(226, 232, 240);
  doc.setLineWidth(0.5);
  doc.line(14, 35, 196, 35);
  
  // Creation metadata
  doc.setFontSize(8);
  doc.setTextColor(148, 163, 184);
  const filterQuery = document.getElementById("admin-search").value.trim();
  doc.text(`Erstellt am: ${new Date().toLocaleString("de-DE")} | Suchfilter: "${filterQuery || 'Keiner'}"`, 14, 41);

  // Stats KPI Card Box
  doc.setFillColor(248, 250, 252);
  doc.roundedRect(14, 46, 182, 38, 3, 3, "F");
  
  doc.setFont("helvetica", "bold");
  doc.setFontSize(11);
  doc.setTextColor(15, 23, 42);
  doc.text("Kennzahlen-Zusammenfassung", 20, 53);
  
  // Recalculate stats for PDF output
  const total = filteredAccounts.length;
  let ageSum = 0;
  let validAges = 0;
  let phoneCount = 0;
  const countries = {};
  const ageGroups = { "Unter 18": 0, "18 - 25": 0, "26 - 40": 0, "41 - 60": 0, "60+": 0 };

  filteredAccounts.forEach(acc => {
    if (acc.birthdate) {
      const parts = acc.birthdate.split('.');
      let birthDate = null;
      if (parts.length === 3) {
        birthDate = new Date(parts[2], parts[1] - 1, parts[0]);
      } else {
        birthDate = new Date(acc.birthdate);
      }
      if (birthDate && !isNaN(birthDate)) {
        const age = Math.floor((new Date() - birthDate) / (365.25 * 24 * 60 * 60 * 1000));
        if (age >= 0 && age < 120) {
          ageSum += age;
          validAges++;
          
          if (age < 18) ageGroups["Unter 18"]++;
          else if (age <= 25) ageGroups["18 - 25"]++;
          else if (age <= 40) ageGroups["26 - 40"]++;
          else if (age <= 60) ageGroups["41 - 60"]++;
          else ageGroups["60+"]++;
        }
      }
    }
    if (acc.phone && acc.phone.trim()) phoneCount++;
    if (acc.country) {
      const c = acc.country.trim();
      countries[c] = (countries[c] || 0) + 1;
    }
  });

  const avgAge = validAges > 0 ? Math.round(ageSum / validAges) : 0;
  const phoneRate = Math.round((phoneCount / total) * 100);
  
  let topCountry = "-";
  let maxCount = 0;
  for (const [c, count] of Object.entries(countries)) {
    if (count > maxCount) {
      maxCount = count;
      topCountry = c;
    }
  }

  doc.setFont("helvetica", "normal");
  doc.setFontSize(9.5);
  doc.setTextColor(51, 65, 85);
  doc.text(`Registrierte Accounts: ${total}`, 20, 61);
  doc.text(`Durchschnittsalter: ${avgAge} Jahre (aus ${validAges} Altersangaben)`, 20, 67);
  doc.text(`Telefon-Ausfuellrate: ${phoneRate}% (${phoneCount} von ${total})`, 20, 73);
  doc.text(`Haeufigstes Land: ${topCountry}`, 20, 79);

  // Left distribution table (Age groups)
  doc.setFont("helvetica", "bold");
  doc.setFontSize(11);
  doc.setTextColor(15, 23, 42);
  doc.text("Altersverteilung", 14, 94);
  
  const ageGroupData = Object.entries(ageGroups).map(([group, count]) => [
    group, 
    `${count} (${total > 0 ? Math.round((count / total) * 100) : 0}%)`
  ]);
  
  doc.autoTable({
    startY: 98,
    head: [["Altersgruppe", "Anzahl / Anteil"]],
    body: ageGroupData,
    theme: "striped",
    headStyles: { fillColor: [241, 245, 249], textColor: [15, 23, 42], fontStyle: "bold" },
    styles: { fontSize: 8.5 },
    margin: { left: 14, right: 105 }
  });

  // Right distribution table (Countries)
  doc.text("Laenderverteilung", 110, 94);
  const countryData = Object.entries(countries).map(([country, count]) => [
    country, 
    `${count} (${total > 0 ? Math.round((count / total) * 100) : 0}%)`
  ]);
  if (countryData.length === 0) countryData.push(["Keine Daten", "0%"]);

  doc.autoTable({
    startY: 98,
    head: [["Land", "Anzahl / Anteil"]],
    body: countryData,
    theme: "striped",
    headStyles: { fillColor: [241, 245, 249], textColor: [15, 23, 42], fontStyle: "bold" },
    styles: { fontSize: 8.5 },
    margin: { left: 110 }
  });

  // Detailed users list section
  const nextStartY = Math.max(doc.lastAutoTable.finalY + 12, 140);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(11);
  doc.text("Registriertes Benutzerverzeichnis", 14, nextStartY - 4);

  const tableRows = filteredAccounts.map(acc => [
    `${acc.first_name || ""} ${acc.last_name || ""}`,
    acc.birthdate || "",
    acc.email || "",
    acc.phone || "Nicht angegeben",
    `${acc.address_line || ""}, ${acc.postal_code || ""} ${acc.city || ""}, ${acc.country || ""}`
  ]);

  doc.autoTable({
    startY: nextStartY,
    head: [["Name", "Geburtsdatum", "E-Mail", "Telefon", "Adresse"]],
    body: tableRows,
    theme: "striped",
    headStyles: { fillColor: [37, 99, 235], textColor: [255, 255, 255] },
    styles: { fontSize: 8 },
    columnStyles: {
      4: { cellWidth: 55 } // Restricts address column to wrap text beautifully
    }
  });

  // Save document as PDF file
  doc.save(`azure_registrations_report_${getTimestamp()}.pdf`);
});
