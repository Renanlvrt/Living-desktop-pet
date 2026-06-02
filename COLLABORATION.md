# Modular Architecture - Team Collaboration Plan

## Project Structure

```
living-desktop-pet/
├── pikachu/                      # Main package
│   ├── __init__.py
│   ├── config.py                 # Global settings
│   ├── main.py                   # Orchestrator (you won't touch this much)
│   │
│   ├── character/
│   │   ├── __init__.py
│   │   ├── base.py               # Abstract character class
│   │   ├── sprite_2d.py          # 2D sprite (current)
│   │   └── sprite_3d.py          # 3D character (future - your friend's work)
│   │
│   ├── movement/
│   │   ├── __init__.py
│   │   ├── engine.py             # Physics & state machine
│   │   └── collision.py          # Window detection & collision resolution
│   │
│   ├── brain/
│   │   ├── __init__.py
│   │   ├── llm.py                # LLM integration (YOUR WORK)
│   │   ├── tts.py                # Text-to-speech (YOUR WORK)
│   │   └── context.py            # Context manager (what Pikachu knows)
│   │
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── window.py             # Main PyQt5 window
│   │   ├── bubble.py             # Speech bubble widget
│   │   └── themes.py             # Styling
│   │
│   └── utils/
│       ├── __init__.py
│       ├── logger.py             # Logging
│       └── helpers.py            # Utility functions
│
├── requirements.txt
├── setup.py
├── pikachu_widget.py             # Legacy launcher (backwards compat)
├── README.md
├── CONFIG.md                     # Configuration guide
└── COLLABORATION.md              # Team workflow guide
```

## Work Division

### Your Work (LLM + TTS + Mechanics)
- **`pikachu/brain/llm.py`**
  - Ollama integration (local LLM)
  - Prompt engineering for Pikachu personality
  - Response cleanup & filtering
  
- **`pikachu/brain/tts.py`** (NEW)
  - Text-to-speech engine
  - Voice selection/customization
  - Audio playback management
  
- **`pikachu/brain/context.py`**
  - Track what Pikachu knows (mood, idle time, recent events)
  - Store conversation history
  - Smart prompt construction
  
- **`pikachu/movement/engine.py`**
  - Enhanced AI for movement choices
  - Emotion-based behavior (happy = bouncy, tired = slow)
  - Event reactions (someone clicked? surprise animation!)

### Your Friend's Work (3D Character)
- **`pikachu/character/sprite_3d.py`**
  - 3D model rendering (Blender export? OpenGL?)
  - Animation states (walking, idle, dancing, etc.)
  - Swap-in replacement for `sprite_2d.py`
  
- **`pikachu/character/base.py`** (interface you define together)
  - Both 2D and 3D must implement same interface
  - Methods: `render()`, `set_position()`, `play_animation()`, `get_bounds()`

### Shared Work
- **`pikachu/main.py`** — Orchestrates everything (you both should understand this)
- **`pikachu/config.py`** — Settings that either of you might add
- **`pikachu/ui/window.py`** — Main event loop & z-order management

---

## Clear Interfaces (So You Don't Step on Each Other)

### Character Interface
```python
# Both 2D sprite and 3D character must implement this
class Character:
    def __init__(self, x, y, scale):
        pass
    
    def render(self, x, y, flip=False):
        """Draw character at (x, y). Return QPixmap or None."""
        pass
    
    def play_animation(self, name: str, loop=False):
        """Play animation: 'walk', 'idle', 'jump', 'surprise', etc."""
        pass
    
    def get_bounds(self):
        """Return (width, height) of bounding box."""
        pass
    
    def update(self, dt):
        """Called every tick for animation updates."""
        pass
```

### LLM Interface
```python
# Your interface - simple and async
class LLMEngine:
    def ask(self, context: str, callback: Callable[[str], None]):
        """
        Ask Pikachu something (non-blocking).
        Calls callback(response) when ready.
        """
        pass
    
    def set_model(self, model: str):
        """Change LLM model."""
        pass
```

### TTS Interface
```python
class TextToSpeech:
    def speak(self, text: str, async=True):
        """Convert text to speech and play."""
        pass
    
    def set_voice(self, voice_name: str):
        """Switch voice."""
        pass
    
    def stop(self):
        """Stop current playback."""
        pass
```

### Movement Engine Interface
```python
class MovementEngine:
    def update(self, obstacles):
        """Update position based on obstacles."""
        return (new_x, new_y, animation_state)
    
    def trigger_event(self, event_type: str, data=None):
        """React to event: 'click', 'escape', 'idle', 'focus'."""
        pass
```

---

## Git Workflow for Collaboration

```bash
# You work on LLM/TTS branch
git checkout -b Renan/llm-and-tts

# Your friend works on 3D branch
git checkout -b seline/3d-character

# Both push regularly
git push -u origin Renan/llm-and-tts
git push -u origin seline/3d-character

# PRs to Renan branch for review before merge
# Renan branch is stable, feature branches branch off from it
```

---

## Development Checklist

- [ ] Create modular package structure
- [ ] Implement Character abstract base class
- [ ] Move current sprite logic to `sprite_2d.py`
- [ ] Implement LLMEngine (Ollama wrapper)
- [ ] Implement TextToSpeech (pyttsx3 or Google TTS)
- [ ] Create speech bubble UI component
- [ ] Implement context manager for Pikachu's "brain"
- [ ] Create orchestrator (`main.py`)
- [ ] Setup logging
- [ ] Write `COLLABORATION.md` with examples
- [ ] Add requirements.txt
- [ ] Test with 2D sprite
- [ ] Document interfaces clearly
- [ ] Ready for 3D integration!

---

## Benefits of This Approach

✅ **Collaboration:** Clear separation means you can work independently
✅ **Scalability:** Easy to add new features without breaking others
✅ **Testing:** Each module can be tested in isolation
✅ **Reusability:** LLM and TTS engines can be used by 3D character too
✅ **Maintenance:** Single source of truth for movement, LLM, TTS
✅ **Future-proof:** Easy to swap 2D for 3D later
✅ **Professional:** Looks great on GitHub/portfolio
