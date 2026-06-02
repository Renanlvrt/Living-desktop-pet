# Architecture Analysis: Speech Bubble & LLM Integration

## Current State

### Master Branch (current)
- **File:** `pikachu_widget.py` (271 lines)
- **Features:** Basic Pikachu sprite with walking, climbing, sitting, falling mechanics
- **No LLM or speech bubble** — purely visual

### Seline Branch (unpushed)
- **File:** `pikachu_widget.py` (411 lines)
- **Features:** 
  - **Speech bubble** with typewriter effect
  - **LLM integration** via Ollama (local LLM server)
  - **Fullscreen detection** (auto-foreground when fullscreen app is active)
  - **Improved movement engine** (2D velocity-based instead of 1D)
  - **Escape behavior** (auto-escape when covered by windows)
  - **Click interaction** (click Pikachu to make him talk)
  - **Context-aware responses** (responds to events)

---

## Speech Bubble Implementation (Seline)

### Visual Design
```python
bubble = QLabel()
bubble.setStyleSheet("""
    QLabel {
        background-color: #fdf6e3;      # Cream background
        border: 2px solid #2b2b2b;      # Dark border
        border-radius: 2px;
        padding: 7px 10px;
        color: #1a1a1a;                 # Dark text
        letter-spacing: 1px;
    }
""")
bubble.setFont(QFont("Courier New", 9, QFont.Bold))
bubble.setMaximumWidth(180)             # Max width to wrap text
```

### Typewriter Effect
```python
TYPE_SPEED = 2  # ticks between character reveals

_type_full    = ""      # Full text to display
_type_index   = 0       # Current character position
_type_delay   = 0       # Ticks until next char
bubble_ticks  = 0       # Remaining ticks to show bubble
```

**How it works:**
1. `show_bubble(text)` sets the full text
2. Every tick, if `bubble_ticks > 0`:
   - Increment `_type_index` every `TYPE_SPEED` ticks
   - Display `_type_full[:_type_index] + "_"` (underscore is cursor)
   - When done, show full text without cursor
3. After `BUBBLE_SHOW_MS` (7 seconds), hide bubble

### Positioning
```python
def _reposition_bubble():
    pw = base_pixmap.width()
    # Center horizontally, place above Pikachu
    bx = int(x) + pw // 2 - bubble.width() // 2
    by = int(y) - bubble.height() - 8   # 8px above
    # Clamp to screen bounds
    bubble.move(max(0, min(bx, screen_w - bubble.width())), max(0, by))
```

---

## LLM Integration (Seline)

### Architecture
```
Pikachu (main thread)
  ↓
ask_llm(context)  → spawns background thread
  ↓
threading.Thread  → makes HTTP request to Ollama
  ↓
Ollama API (localhost:11434)  → tinyllama model
  ↓
Response → emit signal → show_bubble()
```

### Configuration
```python
OLLAMA_MODEL = "tinyllama"
OLLAMA_URL = "http://localhost:11434/api/generate"
```

### How it works
1. **Call `ask_llm(context)`** with situation description
2. **Background thread:**
   - POST to Ollama API with system prompt + context
   - Receive response from tinyllama model
   - Clean text (remove hashtags, max 10 words)
   - Emit signal with cleaned text
3. **Signal handler:** Display bubble with typewriter effect

### System Prompt
```
You are Pikachu, a tiny cute Pokemon living on someone's desktop. 
RULES: 
  - max 10 words total
  - max 1 emoji (optional)
  - No hashtags
  - No punctuation other than ! or ?
  - Cute and expressive
Situation: {context}
```

### Response Examples
- **Idle:** "I have been standing still for a while, just chilling."
  - Pikachu: "Just vibing! ✨" or "I'm so sleepy..."
  
- **Escape:** "I just escaped from behind a window!"
  - Pikachu: "Whew! That was close!" or "Freedom! 🎉"
  
- **Click:** "Someone just clicked on me! I am surprised and happy."
  - Pikachu: "Hey! You poked me!" or "Oh! Hi there! 💛"

---

## Movement Engine Improvements (Seline vs Master)

### Master Branch
- **1D movement:** Only horizontal (direction = ±1)
- **Collision:** Climb, turn around, or sit
- **State machine:** WALKING → IDLE → CLIMBING → SITTING → FALLING
- **Simple push** when overlapped

### Seline Branch
- **2D movement:** vx, vy (velocity components)
- **Direction timer:** Changes direction every 60-250 ticks
- **Random roaming:** More natural, varied movement
- **Fullscreen detection:** Auto-foreground when fullscreen app active
- **Escape state:** Actively tries to escape if covered
- **Simplified states:** ROAMING, IDLE, ESCAPING
- **Bounce physics:** Screen edges bounce character, not clamp

---

## What You Should Do

### Option A: Merge Seline into Renan (Recommended)
```bash
git checkout Renan
git merge origin/seline
```
**Pros:**
- Get all LLM + speech bubble features immediately
- Improved movement engine
- Already tested and polished

**Cons:**
- Requires Ollama running locally
- Two different architectures to reconcile later

### Option B: Cherry-pick Specific Features
Selectively port LLM and speech bubble code from seline to master/Renan.

**Pros:**
- Keep current movement engine if you prefer it
- More control over what features to add

**Cons:**
- More manual work
- Risk of conflicts

### Option C: Start Fresh (Modular Architecture)
Create a clean, modular design:
- `pikachu_sprite.py` — movement & animation
- `speech_bubble.py` — UI component
- `llm_engine.py` — LLM interactions
- `config.py` — settings
- `main.py` — orchestrates everything

**Pros:**
- Professional, maintainable codebase
- Aligns with your "modular and documented" goal
- Easier for contributors
- Can support future features (document interaction, etc.)

**Cons:**
- More work initially
- Need to refactor both master and seline

---

## Requirements for Speech Bubble + LLM

### System
- **Ollama:** Local LLM server running on `localhost:11434`
- **Model:** tinyllama (lightweight, ~1.4B parameters)

### Python Packages
```
PyQt5
Pillow
pywin32
requests  # NEW - for Ollama API calls
```

### Installation
```bash
# Install Ollama from https://ollama.ai
ollama run tinyllama  # Downloads and runs model

# In your project:
pip install requests
```

---

## Next Steps

1. **Decide on approach** (A, B, or C)
2. **Test Seline branch** locally:
   ```bash
   git checkout origin/seline
   ollama run tinyllama
   python pikachu_widget.py
   ```
3. **Document requirements** (add requirements.txt)
4. **Set up CI/tests** if going with modular approach
5. **Plan future features** (document interaction, calendar integration, etc.)

---

## Questions to Clarify

1. **LLM Choice:** Do you want Ollama (local) or cloud API (OpenAI, Anthropic)?
   - Local = private, fast, but needs Ollama server
   - Cloud = simpler setup, but data leaves machine

2. **Merge or Refactor?** Which approach (A, B, or C) aligns with your vision?

3. **Movement:** Do you prefer master's climbing/jumping or seline's smooth roaming?

4. **Performance:** Are you okay with background threads for LLM calls, or need instant responses?

5. **Features Priority:** Speech bubble first? Or async document reading? Or productivity reminders?
