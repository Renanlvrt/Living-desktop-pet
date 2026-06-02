# Living Desktop Pet - Project Overview

## Project Purpose
A creative, emotional desktop companion (Pikachu) for Windows, designed to provide support, motivation, and a touch of fun while you work or study. Pikachu will be able to talk, react to your environment, and eventually help with tasks like suggesting ideas, highlighting spelling mistakes, and more—all while staying out of your way and keeping you focused.

## Current State
- **Platform:** Windows-only (uses win32gui, pywin32, ctypes)
- **Main Script:** `pikachu_widget.py` (PyQt5, Pillow)
- **Assets:** `pikachu.png` (sprite)
- **Launcher:** `launch_pikachu.bat`
- **No README or requirements.txt yet**
- **No modularization or tests yet**

### Features Implemented
- Pikachu sprite walks, climbs, sits, and falls on your desktop
- Avoids covering important UI (taskbar, desktop icons)
- Simple state machine for behavior
- Right-click menu to close
- Handles window collisions and screen edges

### Features Planned / In Progress
- Sound effects and voice
- Chat bubble and notifications
- Productivity features (reminders, encouragement, break suggestions)
- Document interaction (suggestions, corrections, ideas)
- Settings UI for customization
- Multiple sprites/skins
- Persistence across reboots
- Plugin/extension support
- Accessibility and localization
- Installer and portable version
- Automatic updates
- Opt-in anonymous telemetry
- Feedback/reporting system
- Versioning and changelog
- Theme support
- Export/import settings
- Safe mode
- Auto-start on login
- Website/landing page
- System event notifications
- Calendar/to-do integration
- User profiles
- Backup/restore

## Design Principles
- Always visible, but never blocks input or covers important UI
- Modular, documented, and testable codebase
- Creative, original, and non-distracting
- User privacy respected (opt-in telemetry only)
- Local-only data (no cloud sync for now)

## Missing/Needed
- README and documentation site
- requirements.txt
- Modularization and code comments
- Tests and CI
- Installer/packager
- Settings UI
- More assets/skins

---

For a full roadmap, see `FUTURE_IDEAS.md`.
