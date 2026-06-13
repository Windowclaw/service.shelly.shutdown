# Shelly Shutdown Timer Addon für Kodi

Dieses Addon ermöglicht es, einen Shelly Smart Plug Timer auszulösen, wenn Sie die **Aus-Taste auf der Fernbedienung** drücken. Der Shelly schaltet dann sein Ausgangssignal nach einer konfigurierbaren Verzögerung ab und ermöglicht so ein sicheres Herunterfahren des Systems.

## Anforderungen

- **Kodi** (v19+)
- **Shelly Smart Plug** (Gen1 oder Gen2/Gen3) im lokalen Netzwerk
- **Fernbedienung** mit Power-Taste

## Installation & Konfiguration

### 1. Addon installieren

1. **Kodi öffnen** → Einstellungen → Add-ons → Meine Add-ons
2. **"Shelly Shutdown Timer" installieren** (aus ZIP oder Repository)
3. Bei der Installation wird automatisch die remote.xml Keymap erstellt
   - Speicherort: `~/.kodi/userdata/keymaps/remote.xml`
   - **Keine manuelle Bearbeitung erforderlich!**

### 2. Addon-Einstellungen konfigurieren

1. **Kodi öffnen** → Einstellungen → Add-ons → Meine Add-ons
2. Das Addon **"Shelly Shutdown Timer"** auswählen und öffnen
3. Folgende Einstellungen vornehmen:

   **Allgemein:**
   - **Addon aktivieren**: ✓ AN
   - **Shelly-URL**: Die IP-Adresse oder der Hostname des Shelly (z.B. `http://192.168.1.100`)
   - **Shelly-Generation**: Automatisch erkennen ODER manuell wählen (Gen1/Gen2+)
   - **Timer-Verzögerung (s)**: Sekunden bis zur Abschaltung (Standard: 60)

   **Authentifizierung** (falls aktiviert):
   - **Authentifizierung aktivieren**: ✓ AN (nur wenn erforderlich)
   - **Benutzername**: `admin` (Standard)
   - **Passwort**: Ihr Shelly-Passwort

   **Erweitert:**
   - **Request-Timeout (s)**: 5-30 Sekunden
   - **Benachrichtigungen anzeigen**: ✓ AN

### 3. Kodi neu starten

Nach der Installation und Konfiguration **Kodi neustarten**, damit die Keymap geladen wird.

### 4. Fertig! Power-Taste testen

- **Power-Taste auf der Fernbedienung drücken**
- **Benachrichtigung** sollte erscheinen: "Shelly-Timer getriggert: X Sekunden"
- **Kodi fährt herunter** und der Shelly wird nach der konfigurierten Verzögerung abgeschaltet

---

## Automatische Einrichtung

### Was passiert beim Install?

Die `install_keymap.py` wird automatisch aufgerufen und erstellt folgende Datei:

```
~/.kodi/userdata/keymaps/remote.xml
```

Mit diesem Inhalt:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Shelly Shutdown Timer Remote Keymap (v2.0.0) -->
<!-- Generated automatically by service.shelly.shutdown addon -->
<keymap>
    <remote>
        <power>
            RunScript(special://home/addons/service.shelly.shutdown/shelly_timer_cli.py)
        </power>
    </remote>
</keymap>
```

### Keine anderen Fernbedienungs-Funktionen werden geändert

- Nur das `<power>` Event wird überschrieben
- Alle anderen Tasten behalten ihre Standardfunktionen
- Wenn Sie bereits eine `remote.xml` haben, wird diese **nicht überschrieben**

### Bei der Deinstallation

Die `remote.xml` wird **automatisch gelöscht**, wenn das Addon deinstalliert wird (falls sie vom Addon erstellt wurde).

---

## Erweiterte Konfiguration

### Manuelle remote.xml Bearbeitung (optional)

Falls Sie weitere Fernbedienungs-Anpassungen vornehmen möchten, können Sie die `remote.xml` editieren:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<keymap>
    <remote>
        <!-- Shelly Power Button (Addon) -->
        <power>
            RunScript(special://home/addons/service.shelly.shutdown/shelly_timer_cli.py)
        </power>
        
        <!-- Ihre anderen Anpassungen hier: -->
        <home>Action(ActivateWindow(Home))</home>
        <!-- ... weitere Tasten ... -->
    </remote>
</keymap>
```

**Wichtig:** Nach Änderungen an der `remote.xml` **Kodi neustarten**, damit die Änderungen wirksam werden.

### Remote.xml manuell installieren (wenn Automation fehlschlägt)

Falls die Automation nicht funktioniert, können Sie die `remote.xml` auch manuell installieren:

1. Öffnen Sie einen Datei-Manager
2. Navigieren Sie zu `~/.kodi/userdata/keymaps/`
3. Erstellen Sie die Datei `remote.xml` (falls nicht vorhanden)
4. Kopieren Sie den obigen XML-Inhalt rein
5. Speichern und **Kodi neustarten**

---

## Fehlerbehebung

### Problem: "Benachrichtigung wird nicht angezeigt"

- **Lösung:** Prüfen Sie unter Addon-Einstellungen → Erweitert, ob "Benachrichtigungen anzeigen" aktiviert ist

### Problem: "Power-Taste führt nichts aus"

1. Prüfen Sie, dass die `remote.xml` existiert: `~/.kodi/userdata/keymaps/remote.xml`
   ```bash
   ls -la ~/.kodi/userdata/keymaps/remote.xml
   ```

2. **Kodi neu starten** (erforderlich, damit die Keymap geladen wird)

3. Prüfen Sie die Debug-Logs:
   - **Kodi-Einstellungen → System → Protokollierung** (Debug-Modus aktivieren)
   - In der `kodi.log` sollten Sie Einträge wie `[service.shelly.shutdown]` sehen

4. Falls `remote.xml` nicht existiert, können Sie sie manuell erstellen (siehe oben)

### Problem: "Shelly antwortet nicht"

- Prüfen Sie die **Shelly-URL** in den Addon-Einstellungen
- Testen Sie die Verbindung: `curl http://192.168.1.100/shelly` (oder Ihre Shelly-IP)
- Falls SSH-Zugriff auf dem Kodi-System verfügbar ist:
  ```bash
  curl "http://192.168.1.100/relay/0?turn=on&timer=60"  # Gen1
  curl "http://192.168.1.100/rpc/Switch.Set?id=0&on=true&toggle_after=60"  # Gen2/Gen3
  ```

### Problem: "Addon wird nicht installiert"

- Das Addon erfordert **Kodi v19+** und **Python 3.6+**
- Stellen Sie sicher, dass die `addon.xml` korrekt ist
- Prüfen Sie die Kodi-Logs auf Fehler

### Problem: "Bestehende remote.xml wird überschrieben"

- Das sollte nicht passieren! Das Addon schützt vor dem Überschreiben von bestehenden `remote.xml` Dateien
- Falls trotzdem, können Sie die alte Datei sichern und das Addon neu installieren
  ```bash
  cp ~/.kodi/userdata/keymaps/remote.xml ~/.kodi/userdata/keymaps/remote.xml.bak
  ```

---

## Kodi Log-Ausgaben

Die Debug-Logs finden Sie unter:
- **Linux/macOS:** `~/.kodi/temp/kodi.log`
- **Windows:** `%APPDATA%\Kodi\temp\kodi.log`

Relevante Log-Einträge beim Install:
```
[service.shelly.shutdown] ✓ Created keymaps directory: /home/user/.kodi/userdata/keymaps
[service.shelly.shutdown] ✓ Successfully installed remote keymap: /home/user/.kodi/userdata/keymaps/remote.xml
```

Relevante Log-Einträge beim Power-Button:
```
[service.shelly.shutdown] Power button handler: Triggering Shelly timer
[service.shelly.shutdown] ✓ Power button detected - triggering Shelly timer
[service.shelly.shutdown] Shelly responded 200: {"ison":true,"has_timer":true,...}
```

---

## Sicherheit

- **URL-Validierung:** Nur private/lokale IP-Adressen sind erlaubt (SSRF-Schutz)
- **Auth-Credentials:** Werden NICHT in die Logs geschrieben
- **Inline-Credentials:** Nicht unterstützt; verwenden Sie stattdessen die Addon-Einstellungen
- **Timeout-Management:** Verhindert, dass der Shutdown blockiert wird
- **Remote.xml Schutz:** Keine Überschreibung von bestehenden Keymaps

---

## Support & Probleme

Falls Sie Probleme haben:

1. **Debug-Logs aktivieren:** Kodi-Einstellungen → System → Protokollierung (Debug-Modus)
2. **Log-Datei prüfen** (siehe oben)
3. **remote.xml prüfen:**
   ```bash
   cat ~/.kodi/userdata/keymaps/remote.xml
   ```
4. **Shelly direkt testen:**
   ```bash
   # Gen1:
   curl "http://192.168.1.100/relay/0?turn=on&timer=60"
   
   # Gen2/Gen3:
   curl "http://192.168.1.100/rpc/Switch.Set?id=0&on=true&toggle_after=60"
   ```

---

## Lizenz

GPL-2.0-or-later (siehe LICENSE.txt)

## Änderungshistorie

- **v2.0.0**: Automatische remote.xml Installation beim Addon-Install
- **v1.1.0**: Umgestellt auf Fernbedienung-Trigger (Power-Taste) via remote.xml
- **v1.0.0**: Initial Release (automatisch beim Shutdown)
