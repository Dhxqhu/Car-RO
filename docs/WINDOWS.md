# Car-RO on Windows (bay PC client)

Car-RO’s main UI is a **terminal app** (same menus and forms as Linux).  
**ARM Windows** (Snapdragon / Windows on Arm) works if you install **Python for ARM64**.

A full mouse GUI and a Windows `.exe` server are **not** required for day-one use.  
The **server stays on Linux**; this PC is only a client.

---

## What you need

1. Windows 10/11 (x64 or ARM64)  
2. [Python 3.10+](https://www.python.org/downloads/) — during setup, check **“Add python.exe to PATH”**  
3. [Windows Terminal](https://aka.ms/terminal) (recommended)  
4. Car-RO zip from [Releases](https://github.com/Dhxqhu/Car-RO/releases/latest)

---

## Install (copy/paste)

1. Download **Source code (zip)** and unzip (example: `Documents\Car-RO`)  
2. Open **Windows Terminal** or PowerShell  
3. Run:

```powershell
cd $env:USERPROFILE\Documents\Car-RO
# If the unzipped folder has a version suffix, cd into that folder instead
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install.ps1
```

4. Close and reopen the terminal (so PATH updates)  
5. Run:

```powershell
carro
```

If `carro` is not found:

```powershell
& "$env:USERPROFILE\Documents\Car-RO\.venv\Scripts\carro.bat"
```

(or whatever path you unzipped to)

---

## Join the shop server

After the Linux server is set up ([SERVER_SETUP.md](SERVER_SETUP.md)):

```powershell
carro config set server_url http://YOUR_SERVER:8787
carro config set token PASTE_TOKEN_HERE
carro sync
```

Or: `carro` → **`c` Config** → Server URL + API token.

Use the **same** URL and token as every other bay PC.

---

## Day-to-day

| Goal | Command / menu |
| --- | --- |
| Open Car-RO | `carro` |
| Sync | menu **`s`** or `carro sync` |
| Delete mistake RO | menu **`d`** |
| Switch tech | menu **`t`** |

Textual forms need a real terminal (Windows Terminal). The old `cmd.exe` window may look broken.

---

## ARM notes

- Install the **ARM64** Python build on ARM devices (not the x64 emulation build, unless you know you need it).  
- If pip wheels fail for a dependency, say so in an issue with the error text — most of Car-RO’s deps are pure Python / widely wheeled.  

---

## Later ideas (not required yet)

- One-click `carro.exe` via PyInstaller (Release asset)  
- A separate Windows GUI shell  

Those can wait until the terminal client feels solid on your machines.
