# Cyberattack & Defense Turn-Based Simulation (GUI)

An **educational, abstract, turn-based** “Attacker vs Defender” network simulation with two GUI implementations:

* **Tkinter (Desktop GUI)** – classic Windows-style UI, interactive node table, colored logs, and **Save Log to CSV** feature. 
* **Kivy (Cross-platform GUI)** – modern UI layout with spinners, scrollable node table, colored log (markup), and **Save Log to CSV** feature. 

> Safety note: This project is a **game-like simulation**. It does **not** provide real exploit steps and is intended for learning and teaching only.

---

## Features

### Shared game mechanics (both versions)

* **Fixed topology**: Internet → Firewall → DMZ → CorpLAN → (Admin / SIEM / Insider).
* Turn-based phases:

  * **Attacker phase**: limited actions per turn based on attacker “members”
  * **Defender phase**: budget-based defensive actions
* Win/stop conditions:

  * Attacker wins by reaching **exfiltration goal** (`WIN_EXFIL = 100`)
  * Turn limit (`TURN_LIMIT = 14`) determines outcome if time runs out
* Deterministic runs by default (`SEED = 42`) for repeatable demos.

### Attacker actions

* `recon` (raise exposure slightly)
* `social` (influence/bribe Insider; affected by defender awareness)
* `recruit` (spend funds to increase members + skill)
* `exploit` (compromise a node; adjacent foothold helps)
* `lateral` (move from compromised node to adjacent)
* `exfiltrate` (gain value; may be detected)
* `harden` (slight persistence/skill boost)

### Defender actions

* `patch` (reduce exposure, increase patch level)
* `monitor` (increase global detection)
* `awareness` (reduce attacker success for social action)
* `isolate` (cut off node; clears compromise if present)
* `honeypot` (decoy for training/house rules)
* `forensic` (attempt eviction of attacker footholds)

---

## Programs included

### 1) Tkinter GUI (Desktop)

**File:** `cyber_game_gui.py` (your uploaded Tkinter version) 

Highlights:

* Node table with **row coloring**:

  * compromised / isolated / both
* Event log with **colored tags** (attacker red, defender blue)
* **Save Log to CSV** via a file dialog (choose where to save)

Run:

```bash
python cyber_game_gui(tkinter).py
```

### 2) Kivy GUI (Cross-platform)

**File:** `kivy_cyber_game.py` 

Highlights:

* Kivy layout (spinners for actions and targets)
* Scrollable node grid with background highlight for compromised/isolated states
* Event log uses Kivy markup coloring
* **Save Log to CSV** writes to `cyber_game_log.csv` in the current directory

Run:

```bash
python kivy_cyber_game.py
```

---

## Requirements

### Tkinter version

* Python 3.x
* Tkinter (usually included with Python on Windows/macOS)

### Kivy version

* Python 3.x
* Kivy installed:

```bash
pip install kivy
```

---

## How to play

1. Start the program (Tkinter or Kivy).
2. You begin at **Turn 1** in **Attacker phase**.
3. Choose an action and any required target node(s), then execute.
4. End phase to switch to **Defender**, perform defensive actions, then end phase again to go to the next turn.
5. Watch the event log for outcomes (success probability, detection, gained exfiltration value, etc.).

---

## Logs and CSV output

Both versions record structured logs with these fields:

* `turn`, `phase`, `actor`, `message`

* **Tkinter**: you choose the save location via “Save Log to CSV”. 

* **Kivy**: saves to `cyber_game_log.csv` in the current folder and shows a status message. 

---

## Customization points

You can tweak these constants in either file:

* `TOPOLOGY` (network map)
* `BASE_NODES` (node values/exposure)
* `WIN_EXFIL`, `TURN_LIMIT`
* `SEED` (set to `None` for full randomness)

---

## Disclaimer

This project is a **training simulation** for understanding **defense concepts, attacker/defender decision tradeoffs, and incident response dynamics** in a simplified environment. It does **not** model real-world exploitation steps or provide operational guidance.
