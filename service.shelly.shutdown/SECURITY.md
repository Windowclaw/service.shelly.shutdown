# Security & Safety Considerations

## ⚠️ IMPORTANT: Plain-Text Credentials (HTTP)

### Gen1 Devices: No HTTPS Support
Shelly Gen1 devices (Plug, Plug S, 1, 2, etc.) **do not support HTTPS/TLS** due to hardware limitations (ESP8266).

**When using HTTP Basic Authentication with Gen1 devices:**
- Credentials are transmitted as **base64-encoded strings in clear-text HTTP headers**
- Base64 is encoding, NOT encryption
- Any device on your local network can potentially intercept credentials

### Mitigation Strategies

1. **Use a Closed/Trusted Network Only**
   - Only use this addon on private, trusted networks (e.g., home WiFi)
   - Not suitable for guest networks or shared WiFi

2. **No Authentication if Possible**
   - Disable "User Authentication" in addon settings if your Shelly device doesn't require credentials
   - This eliminates the credential transmission risk

3. **Future: HTTPS Support**
   - Gen2/3 devices support HTTPS (though often disabled by default)
   - HTTPS support is planned for a future addon version
   - GitHub Issue: #TODO (HTTPS Gen2/3 support)

4. **Strong Local Network Security**
   - Use WPA3 or at minimum WPA2 encryption on your WiFi
   - Keep router firmware updated
   - Disable WPS (WiFi Protected Setup)

---

## 🔐 Local Credential Storage

### Kodi Settings File (Unencrypted)
This addon stores credentials in Kodi's settings file:
```
~/.kodi/userdata/addon_data/service.shelly.shutdown/settings.xml
```

**Important:**
- Credentials are stored in **plain-text** in this file
- Anyone with file system access to your Kodi device can read them
- On Raspberry Pi with physical access: credentials are trivial to extract

### Recommendations
- Only run this addon on **secured, trusted devices**
- Use strong passwords for your Kodi OS user
- If running on a Raspberry Pi: Use appropriate file system encryption (LUKS) if high security is required
- Regularly review your Shelly device access logs

---

## 🌐 Local Network Only (SSRF Protection)

This addon enforces strict access control:

✅ **Allowed:**
- Private IPv4 ranges: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
- Link-local addresses: `169.254.0.0/16` (Fritz!Box)
- Loopback: `127.0.0.0/8` (testing)

❌ **Blocked:**
- Public/Internet-facing IP addresses
- Prevents accidental or malicious requests to external servers
- Inline credentials in URLs are explicitly rejected

---

## 🔄 Timer Triggering (Intentional Shutdown Only)

### What This Addon DOES
- Triggers Shelly timer **only when user initiates shutdown** via Kodi UI (menu or remote)
- Does not trigger on reboot
- Does not trigger on external shutdown commands (`systemctl shutdown`)
- Does not trigger on system power button

### What This Addon DOES NOT Do
- Does not protect against forceful power cuts (e.g., killing power supply)
- Does not detect "dirty shutdowns" (kernel panic, hardware fault)
- Does not prevent data loss from abrupt power loss before timer expires

---

## 📋 Best Practices

1. **Test Before Production**
   - Test timer functionality thoroughly before relying on it
   - Verify Shelly device responds correctly
   - Monitor logs for connection errors

2. **Use Reasonable Timer Values**
   - Recommended: 10-60 seconds (depends on your system shutdown time)
   - Too short: System may not complete shutdown before power cut
   - Too long: Unnecessary power consumption delay

3. **Monitor Logs**
   - Enable "Show Notifications" in addon settings during setup
   - Check Kodi logs for any connection/auth errors
   - Address any URL validation failures before deploying

4. **Document Your Setup**
   - Write down: Shelly device model, IP address, authentication method
   - Keep this information safe for troubleshooting

---

## 🐛 Report Security Issues

If you discover a security vulnerability in this addon:
- **Do NOT open a public GitHub issue**
- Email security concerns to: [TODO: add security contact]
- Provide details: device model, addon version, network environment, reproduction steps

---

## Version & Support

- **Addon Version:** 1.0.0
- **HTTPS Support:** Planned for v2.0.0
- **Kodi Version:** v18+ (requires xbmc.python 3.0.0+)
- **Tested with:** Gen1 (Plug S), Gen2/3 (Plus Plug S) on HTTP

---

## Legal Disclaimer

This addon is provided "as-is" without warranty. The authors are not responsible for:
- Data loss from power failures
- Damage to hardware or systems
- Interrupted work due to unexpected power cuts
- Misconfiguration of Shelly devices
- Any consequences of network compromise

Use this addon only if you understand and accept these risks.
