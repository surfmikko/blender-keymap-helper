# Blender Keymap Helper

A Blender 5.1+ addon that passively tracks your shortcut usage and surfaces the shortcuts most worth learning right now — used recently, but not yet mastered.

## How it works

The addon runs a background modal operator that watches for keypresses and mouse clicks during normal Blender use. Each shortcut is resolved against the active keymap and recorded with a timestamp and use count. A scoring algorithm weighs recency, learning progress, and mastery to decide which shortcuts to display in the overlay.

The overlay updates automatically when you switch between Object Mode, Edit Mode, Sculpt Mode, or any other context.

### Scoring

Each shortcut is scored as:

```
score = recency × learning × (1 - mastery × 0.95)
```

- **Recency** — decays exponentially from 1.0 as days since last use increases
- **Learning** — rises with use count, caps at 1.0 after ~10 uses
- **Mastery** — rises when both use count and age satisfy the configured thresholds simultaneously; suppresses the score toward zero once a shortcut is well-learned

Shortcuts with a score near zero (too new, too old, or mastered) are hidden. The overlay shows what you are actively in the process of learning.

## Requirements

- Blender 5.1 or later
- Python 3.13 (bundled with Blender)

## Installation

Download the latest zip from the [releases page](../../releases) or build it yourself:

```sh
make dist
```

In Blender: **Edit → Preferences → Add-ons → Install** — select the zip file and enable the addon.

## Development

The Makefile assumes Blender is installed at `/Applications/Blender.app` on macOS. Override with the `BLENDER` variable.

```sh
# Install and symlink for live development (changes take effect on addon reload)
make install

# Open Blender
make blender

# Build distributable zip to dist/
make dist

# Uninstall
make uninstall
```

## Configuration

All options are in **Edit → Preferences → Add-ons → Blender Keymap Helper**.

| Setting | Default | Description |
|---|---|---|
| Position | Bottom Left | Corner of the 3D viewport |
| Horizontal Margin | 20 px | Distance from viewport edge |
| Vertical Margin | 20 px | Distance from viewport bottom |
| Font Size Offset | −2 | Relative to Blender's UI font size |
| Contrast | Low | Low = muted; High = vivid |
| Max Entries | 10 | Maximum shortcuts shown at once |
| Mastery Uses | 20 | Uses required to consider a shortcut learned |
| Mastery Age | 14 days | Days since first use also required for mastery |
| Forget After | 365 days | Remove shortcuts unused for this long |

### Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Shift+H` | Toggle overlay on/off |
| `Ctrl+Shift+Del` | Clear all recorded usage data |

## Data

Usage statistics are stored in JSON at:

```
{Blender config dir}/blender_keymap_helper_data.json
```

The file is written at most once every 30 seconds, and flushed on Blender file load/save. Display names and idnames are resolved at runtime from the active keymap and are never stored.

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).
