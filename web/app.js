let sessionId = null;
let speechAuth = null;
let speechAuthExpiresAt = 0;
const chat = document.getElementById("chat");
const form = document.getElementById("chat-form");
const input = document.getElementById("message");
const voiceBtn = document.getElementById("voice-btn");
const submitBtn = form.querySelector('button[type="submit"]');

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
  const indicator = showTypingIndicator();
  try {
    const response = await fetch("/api/chat/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" }
    });
    const payload = await response.json();
    sessionId = payload.session_id;
    indicator.remove();
    addMessage("bot", payload.reply);
    await speak(payload.reply);
  } catch (err) {
    indicator.remove();
    throw err;
  }
}

async function sendMessage(message) {
  addMessage("user", message);
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

startSession().catch(() => addMessage("bot", "Could not initialize chat session."));
