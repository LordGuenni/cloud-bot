# Konzeptpapier: Entwicklung eines Sprachbots zur Benutzerregistrierung

**Veranstaltung:** Advanced Topics in Cloud Computing (Sommersemester 2026)  
**Dozent:** Prof. Dr.-Ing. Florian Marquardt  
**Eingereicht von:** [Dein Vor- und Nachname]  
**Matrikelnummer:** [Deine Matrikelnummer]  
**Datum:** 04.05.2026

---

## 1. Zielsetzung und Projektübersicht
Im Rahmen dieses Projekts wird ein cloudbasierter Sprachbot entwickelt, der Nutzer durch einen natürlichsprachlichen Dialog führt, um systematisch alle erforderlichen Daten für die Erstellung eines Benutzeraccounts zu erfassen. Die Implementierung stützt sich auf moderne Microsoft Azure-Dienste, um eine robuste Sprachverarbeitung (Speech-to-Text, Text-to-Speech), Intent-Erkennung (CLU) und sichere Datenspeicherung zu gewährleisten.

---

## 2. Dialogfluss (Dialog Flow)
Der nachfolgende Ablauf beschreibt den idealen Pfad ("Happy Path") der Registrierung sowie die integrierte Fehlerbehandlung bei unklaren Eingaben oder unvollständigen Daten.

*Hinweis für die Umsetzung in draw.io: Dieser Text kann als lineares Flussdiagramm mit Rückkopplungsschleifen visualisiert werden.*

1. **Initialisierung & Begrüßung:**
    * **Bot:** "Willkommen! Ich helfe dir bei der Erstellung deines neuen Accounts. Lass uns mit deinen persönlichen Daten beginnen. Wie lauten dein Vor- und Nachname?"
2. **Erfassung Persönliche Daten:**
    * **Nutzer:** Nennt Namen.
    * *System-Aktion:* Extraktion von Vorname und Nachname via Azure CLU.
    * **Bot:** "Danke. Bitte nenne mir nun dein Geburtsdatum."
3. **Erfassung Adressdaten:**
    * **Bot:** "Wie lautet deine vollständige Adresse (Straße, Hausnummer, PLZ, Ort, Land)?"
    * **Nutzer:** Nennt Adresse.
    * *System-Aktion:* Validierung der Adress-Entitäten.
    * *Fehlerbehandlung (Fallback):* Fehlt z. B. die Postleitzahl, fragt der Bot gezielt nach: "Ich habe die Postleitzahl nicht verstanden. Kannst du diese bitte wiederholen?"
4. **Erfassung Kontaktdaten:**
    * **Bot:** "Fast geschafft. Unter welcher E-Mail-Adresse und Telefonnummer bist du erreichbar?"
    * **Nutzer:** Nennt Kontaktdaten.
5. **Validierung & Abschluss:**
    * **Bot:** "Vielen Dank. Ich fasse zusammen: Du heißt [Name], wohnst in [Ort] und deine E-Mail ist [E-Mail]. Sind diese Daten korrekt?"
    * **Nutzer:** "Ja." / "Nein" (Bei "Nein" Rücksprung zur entsprechenden Abfrage).
    * *System-Aktion:* Daten werden über den App Service an die Azure SQL Database übermittelt. Passwörter werden gemäß Anforderung nicht erfasst.
    * **Bot:** "Dein Account wurde erfolgreich angelegt. Auf Wiedersehen!"

---

## 3. Geplante Azure-Architektur
Die Systemarchitektur ist modular aufgebaut und trennt Dialogmanagement, Geschäftslogik und Datenzugriff strikt voneinander.

* **Benutzer-Schnittstelle (Channels):** Die Interaktion erfolgt primär über Voice Chat (Browser) oder Microsoft Teams.
* **Azure Bot Service:** Fungiert als zentraler Router für die verschiedenen Kommunikationskanäle und leitet die Nachrichten an die Applikation weiter.
* **Azure App Service (Node.js / Python):** Hostet das Bot Framework SDK und beinhaltet die Kern-Geschäftslogik, den Dialogfluss (Dialog Management) sowie die Validierungsroutinen.
* **Azure Cognitive Services:**
    * **Speech Services:** Wandelt die gesprochenen Antworten des Nutzers in Text um (Speech-to-Text) und generiert die Sprachausgabe des Bots (Text-to-Speech).
    * **Azure AI Language (CLU):** Analysiert den transkribierten Text, um Absichten (Intents, z. B. `RegistrierungStarten`) zu erkennen und Entitäten (Entities, z. B. `Vorname`, `Stadt`) zu extrahieren.
* **Azure SQL Database:** Dient der relationalen und sicheren Speicherung der validierten Nutzerdaten.
* **Azure Key Vault:** Speichert alle kritischen Geheimnisse, wie Datenbank-Verbindungszeichenfolgen und API-Schlüssel.

---

## 4. Quelltextverwaltung
Der Programmcode, die Dokumentation sowie die CI/CD-Pipelines werden in einem zentralen GitHub-Repository verwaltet.

**Link zum Repository:** [https://github.com/LordGuenni/cloud-bot](https://github.com/LordGuenni/cloud-bot)

---

## 5. Technische Blocker & Cloud Governance (Status: Language Model)
Im Rahmen von Meilenstein 1 wurden die grundlegenden Azure-Ressourcen (Ressourcengruppe, Sprachdienst, Speech Services) erfolgreich in der Region `germanywestcentral` bereitgestellt. Bei der Initialisierung des Conversational Language Understanding (CLU) Modells über die REST-API trat jedoch ein Architektur-Konflikt auf:

Die bereitgestellte Subscription ("Azure for Students") unterliegt in diesem Mandanten einer restriktiven Azure Policy, die das Deployment auf fünf spezifische Regionen limitiert (*spaincentral, uaenorth, polandcentral, germanywestcentral, italynorth*). Laut offizieller Dokumentation unterstützt Microsoft das **Authoring** (Erstellen/Editieren) von CLU-Projekten in diesen Regionen aktuell jedoch nicht (Fehlercode: `UnsupportedFeature`).

Ein Ausweichen auf voll unterstützte Regionen wie `westeurope` wird durch die Tenant-Policy blockiert. Die Vorbereitung der API-Aufrufe (JSON-Bodys für Intents und Entities) wurde dennoch abgeschlossen und dokumentiert. Um den Prototyp für Meilenstein 2 lauffähig zu machen, muss diese Policy-Restriktion im Tenant gelockert werden, oder es muss auf alternative Dienste ausgewichen werden.

---

## 6. Anhang: Nachweis der eingerichteten Azure-Ressourcen
1. **Screenshot 1:** Übersicht der Azure-Ressourcengruppe (ACLOUD) mit den aktiven Diensten.
2. **Screenshot 2:** Dokumentation der Terminal-Ausgabe (curl) zur Projekt-Initialisierung.
3. **Screenshot 3:** Beleg der Fehlermeldung (`UnsupportedFeature`) und Abgleich mit der Microsoft-Verfügbarkeitsmatrix für die Region `germanywestcentral`.
