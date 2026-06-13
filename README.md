# Shelly Shutdown Timer — Kodi Remote Control Integration

[![CI](https://github.com/Windowclaw/service.shelly.shutdown/actions/workflows/ci.yml/badge.svg)](https://github.com/Windowclaw/service.shelly.shutdown/actions/workflows/ci.yml)
![Kodi 19+](https://img.shields.io/badge/Kodi-19%2B-blue)
![Python 3](https://img.shields.io/badge/Python-3-blue)
![License](https://img.shields.io/badge/License-GPL--2.0--or--later-green)

When you press the **Power button on your remote control**, this addon sends an
HTTP request to a **Shelly smart plug** on your local network. The Shelly
cuts power after a configurable delay — giving the system time to complete
shutdown before the socket goes off.

**Use case:** Raspberry Pi running Kodi/OSMC. Pressing "Power off" on the
remote triggers a clean shutdown, then the Shelly cuts the power after e.g.
30–60 seconds. No more standby consumption, no more unsafe power cuts.

> ⚠️ **Security Notice:** This addon currently uses HTTP (not HTTPS) to communicate
> with Shelly devices. Credentials transmitted via HTTP are **not encrypted**.
> **Only use this addon on trusted, closed networks.**
> For detailed security information, see [SECURITY.md](./SECURITY.md)

---

## Features

- **Remote control integration** — triggered by Power button press (via custom remote.xml keymap)
- Works with **Shelly Gen1** (Plug, Plug S, 1, 2 ...) and **Gen2/3** (Plus Plug S, Pro ...)
- **Auto-detection** of Shelly generation via `/shelly` probe
- Configurable **power-off delay** (0–600 seconds)
- Optional **HTTP Basic Auth** (username + password, never logged)
- **SSRF protection**: only private/local network addresses accepted
- **Retry logic**: one automatic retry on transient network errors
- Full **Kodi UI configuration** — no file editing required (except remote.xml)
- Bilingual: **English and German**
- Hardware-independent: runs on any platform Kodi supports

---

## Quick Start

1. **Install this addon** (see [Installation](#installation) below)
2. **Configure the addon settings** in Kodi (Shelly URL, timer delay, etc.)
3. **Restart Kodi** — remote.xml keymap is installed automatically
4. **Press Power button** on your remote — Shelly timer will activate!

For detailed setup instructions, see [INSTALLATION.md](./service.shelly.shutdown/INSTALLATION.md).

---

## Installation

### Option A — Install from ZIP (simplest)

1. Download the latest `service.shelly.shutdown-x.x.x.zip` from
   [Releases](https://github.com/Windowclaw/service.shelly.shutdown/releases)
2. In Kodi: *Settings → Addons → Install from ZIP file*
3. Navigate to the downloaded ZIP and confirm

> If the ZIP installer does not work (known issue on some platforms), install
> manually:
> ```bash
> unzip service.shelly.shutdown-*.zip -d ~/.kodi/addons/
> sudo systemctl restart mediacenter   # OSMC/LibreELEC
> ```

### Option B — Install via Repository

1. Download `repository.windowclaw.shelly-1.0.0.zip` from
   [Releases](https://github.com/Windowclaw/service.shelly.shutdown/releases)
2. In Kodi: *Settings → Addons → Install from ZIP file* → select the
   repository ZIP
3. Then: *Settings → Addons → Install from repository → Windowclaw Shelly
   Repository → Services → Shelly Shutdown Timer → Install*

The repository addon points to GitHub Pages and supports **automatic updates**.

---

## Configuration

### Step 1: Addon Settings

Open the addon settings in Kodi:
*Settings → Addons → My addons → Services → Shelly Shutdown Timer → Configure*

| Setting | Description |
|---|---|
| **Enable addon** | Master on/off switch |
| **Shelly device URL** | Base URL of your Shelly, e.g. `http://192.168.1.100` or `http://shellyplug-s.fritz.box` |
| **Auto-detect generation** | Probe the Shelly to auto-detect Gen1/Gen2 |
| **Shelly generation** | Manual selection (Gen1 or Gen2/3); used if auto-detect is off |
| **Power-off delay** | Seconds between Power button press and Shelly cutting power (0–600 s) |
| **HTTP request timeout** | How long to wait for the Shelly to respond (1–30 s) |
| **Show notifications** | Display OSD confirmation/error when Power button is pressed |

### Authentication (if needed)

| Setting | Description |
|---|---|
| **Enable HTTP authentication** | Enable if your Shelly has "Restrict Login" enabled |
| **Username** | HTTP Basic Auth username (default: `admin`) |
| **Password** | HTTP Basic Auth password (masked in UI, never written to logs) |

### Step 2: Automatic Remote Control Keymap Setup

When you **install the addon**, the `install_keymap.py` script is automatically executed:

- ✅ Creates `~/.kodi/userdata/keymaps/remote.xml` (if it doesn't exist)
- ✅ Maps Power button to the Shelly timer script
- ✅ Protects existing keymaps from being overwritten
- ✅ Generates a minimal, clean remote.xml with only the Power override

**No manual editing required!** Just install and restart Kodi.

---

## Shelly API endpoints used

| Generation | Endpoint |
|---|---|
| Gen1 | `GET /relay/0?turn=on&timer=<seconds>` |
| Gen2/3 | `GET /rpc/Switch.Set?id=0&on=true&toggle_after=<seconds>` |
| Detection probe | `GET /shelly` |

---

## Recommended delay values

| Hardware | Suggested delay |
|---|---|
| Raspberry Pi 3B/3B+ | 45–60 s |
| Raspberry Pi 4 | 30–45 s |
| x86 PC (SSD) | 20–30 s |
| x86 PC (HDD) | 30–60 s |

When in doubt, set a generous value. The Shelly will simply stay on a bit
longer — no harm done.

---

## Development

```bash
# Clone
git clone https://github.com/Windowclaw/service.shelly.shutdown.git
cd service.shelly.shutdown

# Run tests (no Kodi installation required)
python3 -m unittest discover -s tests -v

# Syntax check
python3 -m py_compile service.shelly.shutdown/service.py
python3 -m py_compile service.shelly.shutdown/shelly_client.py
```

### Repository structure

```
/
├── .github/
│   └── workflows/
│       └── ci.yml                  CI: test, build, deploy to GitHub Pages
├── service.shelly.shutdown/        Kodi addon source
│   ├── addon.xml
│   ├── service.py                  Service entry point (xbmc.service)
│   ├── shelly_client.py            Shelly HTTP API + security layer
│   ├── LICENSE.txt
│   ├── changelog.txt
│   ├── icon.png                    256x256
│   ├── fanart.png                  1280x720
│   └── resources/
│       ├── settings.xml
│       └── language/
│           ├── resource.language.en_gb/strings.po
│           └── resource.language.de_de/strings.po
├── repository.windowclaw.shelly/   Kodi repository addon
│   ├── addon.xml
│   └── icon.png
├── tests/
│   ├── __init__.py
│   └── test_shelly_client.py       39 unit tests (no Kodi needed)
└── README.md
```

The CI pipeline automatically:
1. Runs all 39 unit tests on Python 3.9 – 3.12
2. Validates all XML files
3. Checks the addon structure for required files
4. Builds the ZIP files and `addons.xml`
5. Deploys `addons.xml`, `addons.xml.md5` and the ZIPs to the `gh-pages`
   branch, which serves as the live Kodi repository

---

## Compatibility

| Kodi version | Codename | Status |
|---|---|---|
| 19 | Matrix | ✅ |
| 20 | Nexus | ✅ |
| 21 | Omega | ✅ (tested) |

---

## License

GPL-2.0-or-later — see [LICENSE.txt](service.shelly.shutdown/LICENSE.txt)
# service.shelly.shutdown
