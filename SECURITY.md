# Security Policy — Living Desktop Pet

## How Secrets Are Protected

This project handles sensitive data (Google OAuth2 tokens, API credentials).
Below is a full description of every security measure in place.

---

## 1. Encryption Architecture (Defence-in-Depth)

All sensitive files are stored **encrypted** in `~/.pikachu/`.
**Plain-text credentials NEVER touch disk.**

```
Layer 1  Windows Credential Manager  ←  stores the 32-byte master key
           (backed by Windows DPAPI, bound to your Windows user login)
                    ↓
Layer 2  Fernet (AES-128-CBC + HMAC-SHA256)  ←  encrypts JSON blobs
           (python `cryptography` library)
                    ↓
  ~/.pikachu/token.enc          (Google OAuth token — encrypted)
  ~/.pikachu/credentials.enc   (Google app credentials — encrypted)
```

### How it works

| Step | Action |
|------|--------|
| First run | App generates a cryptographically random 32-byte master key |
| | Key is stored in **Windows Credential Manager** (encrypted by Windows using your login password via DPAPI) |
| Every save | Secret JSON → JSON string → Fernet.encrypt(AES) → `.enc` file |
| Every load | `.enc` file → Fernet.decrypt(AES) → JSON string → Python dict |
| Theft scenario | If someone steals your `.enc` files, they are **useless** without the master key |
| | The master key is only readable by your Windows user account |

---

## 2. Files That Are NEVER Committed to Git

The `.gitignore` blocks all sensitive file types:

```
credentials.json        ← Google app credentials
token.json              ← OAuth2 token
client_secret*.json     ← Any Google client secret variant
*.key / *.pem / *.p12   ← Private keys and certificates
*.enc                   ← Encrypted vault files
.env / .env.*           ← Environment variable files
secrets.json / secrets.yaml
*.db / *.sqlite         ← Local caches (may contain personal data)
```

---

## 3. Pre-Commit Hook

A Git pre-commit hook (`scripts/pre-commit`) **blocks every commit** that
would accidentally expose a secret.

### Install the hook (run once)

```bash
python scripts/install_hooks.py
```

### What the hook checks

1. **Blocked filenames** — e.g. `token.json`, `credentials.json`, `.env`
2. **Content patterns** — scans staged file content for:
   - `"client_secret"`, `"refresh_token"`, `"access_token"` JSON keys
   - API key patterns (`api_key = "..."`, `secret_key = "..."`)
   - AWS Access Key IDs (`AKIA...`)
   - Private key headers (`-----BEGIN ... PRIVATE KEY-----`)
   - Generic password literals
3. **File size guard** — warns about files >500 KB

If any check fails, the commit is **blocked** with a clear error message.

---

## 4. Key Rotation

If you suspect the master key may be compromised, you can rotate it:

```python
from pikachu.utils.vault import rotate_master_key
rotate_master_key()
```

This will:
1. Decrypt all secrets with the old key
2. Generate a fresh 32-byte key
3. Store the new key in Windows Credential Manager
4. Re-encrypt all secrets with the new key

---

## 5. What Happens If You Change Windows User / Reinstall Windows?

The master key is bound to your Windows user account via DPAPI.
**If you lose access to your Windows user account, the master key is lost.**

**Before reinstalling Windows or migrating PCs:**
1. Log in to Google and revoke the app's OAuth token
2. Go through the Google Calendar setup again on the new machine
3. The new machine will generate its own fresh master key

---

## 6. Scanning Your Repo for Past Leaks

If you suspect a secret was accidentally committed in the past:

```powershell
# Install gitleaks (Windows)
winget install --id GitTools.Gitleaks

# Scan the entire git history
gitleaks detect --source . --log-opts="--all"
```

If gitleaks finds something, **immediately revoke** the exposed credential
in Google Cloud Console → APIs & Services → Credentials.

---

## 7. Summary Table

| Threat | Protection |
|--------|-----------|
| Someone copies `~/.pikachu/*.enc` | Fernet AES encryption — unreadable without master key |
| Someone reads Windows Credential Manager | Requires your Windows login password (DPAPI) |
| Accidental `git push` of `token.json` | `.gitignore` + pre-commit hook blocks it |
| Compromised master key | `rotate_master_key()` re-encrypts everything |
| Stolen laptop (different Windows user) | DPAPI is user-bound — decryption fails |
