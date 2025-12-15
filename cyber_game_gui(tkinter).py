"""
GUI Attacker vs Defender (Educational & Safe) — PLUS
- Tkinter interface for an abstract, turn-based network defense game.
- Adds: Save Log to CSV, colored log tags, and row coloring for compromised/isolated nodes.

Run: python gui_cyber_game_plus.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import csv
import random
from collections import defaultdict

# ======= Core Game Config =======
TOPOLOGY = {
    "Internet": ["Firewall"],
    "Firewall": ["Internet", "DMZ"],
    "DMZ": ["Firewall", "CorpLAN"],
    "CorpLAN": ["DMZ", "Admin", "Insider", "SIEM"],
    "Admin": ["CorpLAN"],
    "SIEM": ["CorpLAN"],
    "Insider": ["CorpLAN"]
}

BASE_NODES = {
    "Internet": {"value": 0,  "exposure": 1.00, "is_compromised": False},
    "Firewall": {"value": 5,  "exposure": 0.20, "is_compromised": False},
    "DMZ":      {"value": 10, "exposure": 0.40, "is_compromised": False},
    "CorpLAN":  {"value": 20, "exposure": 0.60, "is_compromised": False},
    "Admin":    {"value": 30, "exposure": 0.30, "is_compromised": False},
    "SIEM":     {"value": 15, "exposure": 0.25, "is_compromised": False},
    "Insider":  {"value": 8,  "exposure": 0.50, "is_compromised": False},
}

WIN_EXFIL = 100
TURN_LIMIT = 14
SEED = 42  # set to None for full randomness

ATTACKER_ACTIONS = [
    ("recon", "Learn a node & raise exposure slightly (low detection)"),
    ("social", "Influence/Bribe the Insider (awareness reduces success)"),
    ("recruit", "Spend funds to add a member and +1 skill"),
    ("exploit", "Try to compromise a node (adjacent foothold helps)"),
    ("lateral", "Move from a compromised node to an adjacent node"),
    ("exfiltrate", "Exfiltrate from a compromised node"),
    ("harden", "Improve persistence slightly on a compromised node"),
]

DEFENDER_ACTIONS = [
    ("patch", "Reduce exposure & raise patch level on a node"),
    ("monitor", "Increase global detection probability"),
    ("awareness", "Reduce success of social influence attempts"),
    ("isolate", "Cut off a node; remove compromise if present"),
    ("honeypot", "Deploy a decoy (narrative/house rule effect)"),
    ("forensic", "Attempt to evict attacker from compromised nodes"),
]

# ======= Utilities =======
def deep_copy_nodes():
    return {k: v.copy() for k, v in BASE_NODES.items()}

def chance_success(base_prob, attacker_skill=0.0, defender_patch=0, modifiers=1.0):
    skill_factor = 1 + (attacker_skill / 10.0)
    patch_factor = max(0.0, 1 - (defender_patch / 12.0))
    p = base_prob * skill_factor * modifiers * patch_factor
    p = max(0.0, min(0.95, p))
    roll = random.random()
    return (roll < p), p, roll

def detection_check(base_detection, defender_monitoring, stealth_mod=1.0):
    p = base_detection * defender_monitoring * stealth_mod
    p = max(0.0, min(0.99, p))
    roll = random.random()
    return (roll < p), p, roll

# ======= Game State =======
class Attacker:
    def __init__(self):
        self.funds = 50
        self.skill = 5.0
        self.influence = 1.0
        self.members = 1
        self.compromised = set()
        self.exfiltrated_value = 0

class Defender:
    def __init__(self):
        self.budget = 60
        self.patch_level = defaultdict(lambda: 0)
        self.monitoring = 1.0
        self.awareness = 1.0
        self.isolated = set()
        self.honeypots = set()

# ======= Mechanics (Attacker) =======
def act_recon(att, dfn, nodes, node):
    base = 0.6
    succ, p, r = chance_success(base, att.skill, dfn.patch_level[node], 1.0)
    det, dp, dr = detection_check(0.05, dfn.monitoring, 0.8)
    if succ:
        nodes[node]['exposure'] = min(1.0, nodes[node]['exposure'] + 0.1)
    return f"Recon {node} -> success={succ} (p={p:.2f}), detected={det} (p={dp:.2f})", det, "attacker"

def act_social(att, dfn, nodes, node="Insider"):
    base = 0.35 * att.influence
    succ, p, r = chance_success(base, att.skill, dfn.patch_level[node], modifiers=1.0/dfn.awareness)
    det, dp, dr = detection_check(0.15, dfn.monitoring, 1.2)
    if succ:
        nodes[node]['is_compromised'] = True
        att.compromised.add(node)
    return f"Social influence {node} -> success={succ} (p={p:.2f}), detected={det} (p={dp:.2f})", det, "attacker"

def act_recruit(att):
    cost = 15
    if att.funds >= cost:
        att.funds -= cost
        att.members += 1
        att.skill += 1.0
        return "Recruit -> success (members+1, skill+1)", False, "attacker"
    return "Recruit -> failed (insufficient funds)", False, "attacker"

def act_exploit(att, dfn, nodes, target):
    if target in dfn.isolated:
        return f"Exploit {target} -> aborted (isolated)", False, "attacker"
    base = nodes[target]['exposure']
    adj_compromised = any(adj in att.compromised for adj in TOPOLOGY.get(target, []))
    mod = 1.3 if adj_compromised else 1.0
    succ, p, r = chance_success(base, att.skill, dfn.patch_level[target], mod)
    det, dp, dr = detection_check(0.1 + nodes[target]['value']/100.0, dfn.monitoring, 0.9)
    if succ:
        nodes[target]['is_compromised'] = True
        att.compromised.add(target)
    return (f"Exploit {target} -> success={succ} (p={p:.2f}), detected={det} "
            f"(p={dp:.2f}), adj_comp={adj_compromised}"), det, "attacker"

def act_lateral(att, dfn, nodes, src, dst):
    if src not in att.compromised:
        return f"Lateral {src}->{dst} -> failed (source not compromised)", False, "attacker"
    if dst not in TOPOLOGY.get(src, []):
        return f"Lateral {src}->{dst} -> failed (not adjacent)", False, "attacker"
    base = 0.4 + (nodes[dst]['exposure'] * 0.3)
    succ, p, r = chance_success(base, att.skill, dfn.patch_level[dst], 1.0)
    det, dp, dr = detection_check(0.12, dfn.monitoring, 1.0)
    if succ:
        nodes[dst]['is_compromised'] = True
        att.compromised.add(dst)
    return f"Lateral {src}->{dst} -> success={succ} (p={p:.2f}), detected={det} (p={dp:.2f})", det, "attacker"

def act_exfiltrate(att, dfn, nodes, node):
    if node not in att.compromised:
        return f"Exfiltrate {node} -> failed (not compromised)", False, "attacker"
    succ, p, r = chance_success(0.5, att.skill, dfn.patch_level[node], 1.0)
    det, dp, dr = detection_check(0.25 + nodes[node]['value']/100.0, dfn.monitoring, 1.0)
    gained = int(nodes[node]['value'] * random.uniform(0.5, 1.0)) if succ else 0
    if succ:
        att.exfiltrated_value += gained
        att.funds += int(gained * 0.5)
    return f"Exfiltrate {node} -> success={succ} (p={p:.2f}), detected={det} (p={dp:.2f}), gained={gained}", det, "attacker"

def act_harden(att, node):
    if node not in att.compromised:
        return f"Harden {node} -> failed (not compromised)", False, "attacker"
    att.skill += 0.2
    return f"Harden {node} -> persistence improved slightly (skill+0.2)", False, "attacker"

# ======= Mechanics (Defender) =======
def def_patch(dfn, nodes, node):
    cost = 8
    if dfn.budget < cost:
        return "Patch -> failed (insufficient budget)", "defender"
    dfn.budget -= cost
    dfn.patch_level[node] = min(10, dfn.patch_level[node] + 2)
    nodes[node]['exposure'] = max(0.05, nodes[node]['exposure'] - 0.15)
    return f"Patch {node} -> success (patch={dfn.patch_level[node]}, exposure={nodes[node]['exposure']:.2f})", "defender"

def def_monitor(dfn):
    cost = 6
    if dfn.budget < cost:
        return "Monitoring -> failed (insufficient budget)", "defender"
    dfn.budget -= cost
    dfn.monitoring = min(3.0, dfn.monitoring + 0.3)
    return f"Monitoring -> increased (now {dfn.monitoring:.2f})", "defender"

def def_awareness(dfn):
    cost = 10
    if dfn.budget < cost:
        return "Awareness -> failed (insufficient budget)", "defender"
    dfn.budget -= cost
    dfn.awareness = max(0.5, dfn.awareness - 0.2)
    return f"Awareness -> campaign run (awareness now {dfn.awareness:.2f})", "defender"

def def_isolate(dfn, nodes, node):
    cost = 12
    if dfn.budget < cost:
        return "Isolate -> failed (insufficient budget)", "defender"
    dfn.budget -= cost
    dfn.isolated.add(node)
    if nodes[node]['is_compromised']:
        nodes[node]['is_compromised'] = False
    return f"Isolate {node} -> success (segment cut; compromise removed if present)", "defender"

def def_honeypot(dfn, node):
    cost = 7
    if dfn.budget < cost:
        return "Honeypot -> failed (insufficient budget)", "defender"
    dfn.budget -= cost
    dfn.honeypots.add(node)
    return f"Honeypot near {node} -> deployed", "defender"

def def_forensic(dfn, att, nodes):
    cost = 10
    if dfn.budget < cost:
        return "Forensic -> failed (insufficient budget)", "defender"
    dfn.budget -= cost
    compromised_count = len(att.compromised)
    base = 0.4 + 0.05 * compromised_count
    p = min(0.9, base * dfn.monitoring)
    succ = random.random() < p
    if succ and compromised_count:
        rem_ct = max(1, compromised_count // 2)
        removed = []
        for node in list(att.compromised)[:rem_ct]:
            nodes[node]['is_compromised'] = False
            att.compromised.discard(node)
            removed.append(node)
        att.funds = max(0, att.funds - 10)
        att.skill = max(1.0, att.skill - 0.5)
        return f"Forensic -> success (evicted {removed}, attacker -10 funds, -0.5 skill)", "defender"
    return "Forensic -> no conclusive findings", "defender"

# ======= GUI App =======
class GameApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Attacker vs Defender (Educational Simulation)")
        self.geometry("1140x760")
        if SEED is not None:
            random.seed(SEED)

        # State
        self.turn = 1
        self.nodes = deep_copy_nodes()
        self.att = Attacker()
        self.dfn = Defender()
        self.att_actions_used = 0
        self.phase = "attacker"  # "attacker" or "defender"

        # Logging (for CSV)
        # Each record: {"turn": int, "phase": str, "actor": str, "message": str}
        self.log_records = []

        self.create_widgets()
        self.refresh_all()
        self.log_line("==== Turn 1 ====", tag="system")

    # ---------- UI Layout ----------
    def create_widgets(self):
        # Top frame: status & controls
        top = ttk.Frame(self, padding=8)
        top.pack(side=tk.TOP, fill=tk.X)

        self.turn_label = ttk.Label(top, text="Turn: 1", font=("Segoe UI", 12, "bold"))
        self.turn_label.pack(side=tk.LEFT, padx=(0, 16))

        self.att_status = ttk.Label(top, text="", font=("Segoe UI", 10))
        self.att_status.pack(side=tk.LEFT, padx=8)

        self.dfn_status = ttk.Label(top, text="", font=("Segoe UI", 10))
        self.dfn_status.pack(side=tk.LEFT, padx=8)

        # Phase indicator
        self.phase_label = ttk.Label(top, text="Phase: Attacker", foreground="#993333", font=("Segoe UI", 11, "bold"))
        self.phase_label.pack(side=tk.RIGHT)

        # Middle pane: left (nodes) + right (actions)
        mid = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        mid.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Left: Nodes table
        left = ttk.Frame(mid, padding=4)
        mid.add(left, weight=1)

        lbl_nodes = ttk.Label(left, text="Network Nodes", font=("Segoe UI", 11, "bold"))
        lbl_nodes.pack(anchor="w")

        cols = ("node", "value", "exposure", "compromised", "isolated", "patch")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=20)
        for c, w in zip(cols, (160, 60, 80, 100, 80, 60)):
            self.tree.heading(c, text=c.capitalize())
            self.tree.column(c, width=w, anchor="center")
        self.tree.pack(fill=tk.BOTH, expand=True, pady=4)

        # Configure row tags (colors)
        # Note: ttk.Treeview supports tag configuration for foreground/background
        self.tree.tag_configure("row_compromised", background="#ffe6e6")
        self.tree.tag_configure("row_isolated", background="#fff3cd")
        self.tree.tag_configure("row_both", background="#ffd6d6")  # compromised + isolated

        # Right: Actions & targets
        right = ttk.Frame(mid, padding=4)
        mid.add(right, weight=1)

        self.actions_frame = ttk.LabelFrame(right, text="Actions", padding=8)
        self.actions_frame.pack(fill=tk.X)

        # Action selection
        ttk.Label(self.actions_frame, text="Choose Action:").grid(row=0, column=0, sticky="w")
        self.action_var = tk.StringVar()
        self.action_combo = ttk.Combobox(self.actions_frame, textvariable=self.action_var, state="readonly", width=32)
        self.action_combo.grid(row=0, column=1, sticky="w", padx=6)

        # Target inputs (contextual)
        self.target_a_label = ttk.Label(self.actions_frame, text="Target:")
        self.target_a_combo = ttk.Combobox(self.actions_frame, state="readonly", width=32)
        self.target_b_label = ttk.Label(self.actions_frame, text="Destination:")
        self.target_b_combo = ttk.Combobox(self.actions_frame, state="readonly", width=32)

        # Buttons
        btns = ttk.Frame(self.actions_frame)
        btns.grid(row=4, column=0, columnspan=2, pady=(8,0), sticky="w")
        self.execute_btn = ttk.Button(btns, text="Execute Action", command=self.on_execute)
        self.execute_btn.grid(row=0, column=0, padx=(0,6))
        self.op_exfil_btn = ttk.Button(btns, text="Opportunistic Exfil (Attacker)", command=self.on_op_exfil)
        self.op_exfil_btn.grid(row=0, column=1, padx=6)
        self.end_phase_btn = ttk.Button(btns, text="End Phase", command=self.on_end_phase)
        self.end_phase_btn.grid(row=0, column=2, padx=6)

        # Save Log to CSV
        self.save_csv_btn = ttk.Button(btns, text="Save Log to CSV", command=self.on_save_csv)
        self.save_csv_btn.grid(row=0, column=3, padx=6)

        # Defender bonus action rule (visual hint only)
        self.def_bonus_var = tk.BooleanVar(value=False)
        self.def_bonus_chk = ttk.Checkbutton(self.actions_frame, text="Defender allows second action when budget ≥ 20", variable=self.def_bonus_var)
        self.def_bonus_chk.grid(row=5, column=0, columnspan=2, pady=(6,0), sticky="w")

        # Bottom: Log
        log_frame = ttk.LabelFrame(self, text="Event Log", padding=6)
        log_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, padx=8, pady=(0,8))

        self.log = tk.Text(log_frame, height=10, wrap="word")
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(log_frame, command=self.log.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.log["yscrollcommand"] = sb.set

        # Configure colored text tags
        self.log.tag_configure("attacker", foreground="#cc0000")
        self.log.tag_configure("defender", foreground="#004aad")
        self.log.tag_configure("system",   foreground="#666666")

        # Bind
        self.action_combo.bind("<<ComboboxSelected>>", self.on_action_change)

    # ---------- Refresh UI ----------
    def refresh_all(self):
        # statuses
        self.turn_label.config(text=f"Turn: {self.turn}")
        self.att_status.config(text=f"Attacker  | funds={self.att.funds}  skill={self.att.skill:.1f}  infl={self.att.influence:.2f}  members={self.att.members}  exfil={self.att.exfiltrated_value}")
        self.dfn_status.config(text=f"Defender  | budget={self.dfn.budget}  monitor={self.dfn.monitoring:.2f}  awareness={self.dfn.awareness:.2f}")

        # table
        for i in self.tree.get_children():
            self.tree.delete(i)
        for n in sorted(self.nodes.keys()):
            d = self.nodes[n]
            compromised = "Yes" if d["is_compromised"] else "No"
            isolated = "Yes" if n in self.dfn.isolated else "No"
            patch = self.dfn.patch_level[n]
            # Apply row tag for coloring
            row_tags = ()
            if d["is_compromised"] and (n in self.dfn.isolated):
                row_tags = ("row_both",)
            elif d["is_compromised"]:
                row_tags = ("row_compromised",)
            elif n in self.dfn.isolated:
                row_tags = ("row_isolated",)
            self.tree.insert("", "end", values=(n, d["value"], f"{d['exposure']:.2f}", compromised, isolated, patch), tags=row_tags)

        # phase UI setup
        if self.phase == "attacker":
            self.phase_label.config(text=f"Phase: Attacker (actions used {self.att_actions_used}/{self.att.members})", foreground="#993333")
            self.action_combo["values"] = [f"{k} – {desc}" for k, desc in ATTACKER_ACTIONS]
            self.action_combo.set("")  # reset
            self.op_exfil_btn.state(["!disabled"])
        else:
            self.phase_label.config(text=f"Phase: Defender", foreground="#336699")
            self.action_combo["values"] = [f"{k} – {desc}" for k, desc in DEFENDER_ACTIONS]
            self.action_combo.set("")
            self.op_exfil_btn.state(["disabled"])

        self.hide_targets()

    def hide_targets(self):
        for w in (self.target_a_label, self.target_a_combo, self.target_b_label, self.target_b_combo):
            w.grid_forget()
        self.target_a_combo.set("")
        self.target_b_combo.set("")

    def on_action_change(self, *_):
        self.hide_targets()
        action_text = self.action_var.get() or self.action_combo.get()
        if not action_text:
            return
        key = action_text.split(" – ")[0]

        if self.phase == "attacker":
            if key in ("recon", "exploit"):
                self.target_a_label.config(text="Target:")
                self.target_a_label.grid(row=1, column=0, sticky="w", pady=(6,0))
                self.target_a_combo["values"] = list(self.nodes.keys())
                self.target_a_combo.grid(row=1, column=1, sticky="w", padx=6, pady=(6,0))

            elif key == "lateral":
                self.target_a_label.config(text="From (compromised):")
                self.target_a_label.grid(row=1, column=0, sticky="w", pady=(6,0))
                self.target_a_combo["values"] = sorted(self.att.compromised)
                self.target_a_combo.grid(row=1, column=1, sticky="w", padx=6, pady=(6,0))

                self.target_b_label.config(text="To (adjacent):")
                self.target_b_label.grid(row=2, column=0, sticky="w", pady=(6,0))
                self.target_a_combo.bind("<<ComboboxSelected>>", self.update_lateral_dest)

            elif key in ("exfiltrate", "harden"):
                self.target_a_label.config(text="Select node:")
                self.target_a_label.grid(row=1, column=0, sticky="w", pady=(6,0))
                self.target_a_combo["values"] = sorted(self.att.compromised)
                self.target_a_combo.grid(row=1, column=1, sticky="w", padx=6, pady=(6,0))

        else:  # Defender
            if key in ("patch", "isolate", "honeypot"):
                self.target_a_label.config(text="Target node:")
                self.target_a_label.grid(row=1, column=0, sticky="w", pady=(6,0))
                self.target_a_combo["values"] = list(self.nodes.keys())
                self.target_a_combo.grid(row=1, column=1, sticky="w", padx=6, pady=(6,0))

    def update_lateral_dest(self, *_):
        src = self.target_a_combo.get()
        self.target_b_combo["values"] = TOPOLOGY.get(src, [])
        self.target_b_combo.grid(row=2, column=1, sticky="w", padx=6, pady=(6,0))

    # ---------- Action handlers ----------
    def log_line(self, text, tag="system", actor=None):
        """Append a colored line to the log and also store a structured record for CSV."""
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END, text + "\n", (tag,))
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)
        # store
        self.log_records.append({
            "turn": self.turn,
            "phase": self.phase,
            "actor": actor if actor else tag,
            "message": text
        })

    def on_execute(self):
        action_text = self.action_combo.get()
        if not action_text:
            messagebox.showinfo("Select Action", "Please choose an action first.")
            return
        key = action_text.split(" – ")[0]

        if self.phase == "attacker":
            if key == "recruit":
                msg, det, who = act_recruit(self.att)
            elif key == "social":
                msg, det, who = act_social(self.att, self.dfn, self.nodes)
            elif key == "recon":
                target = self.target_a_combo.get()
                if not target:
                    messagebox.showinfo("Target required", "Pick a target node.")
                    return
                msg, det, who = act_recon(self.att, self.dfn, self.nodes, target)
            elif key == "exploit":
                target = self.target_a_combo.get()
                if not target:
                    messagebox.showinfo("Target required", "Pick a target node.")
                    return
                msg, det, who = act_exploit(self.att, self.dfn, self.nodes, target)
            elif key == "lateral":
                src = self.target_a_combo.get()
                dst = self.target_b_combo.get()
                if not src or not dst:
                    messagebox.showinfo("Targets required", "Pick source and destination nodes.")
                    return
                msg, det, who = act_lateral(self.att, self.dfn, self.nodes, src, dst)
            elif key == "exfiltrate":
                node = self.target_a_combo.get()
                if not node:
                    messagebox.showinfo("Target required", "Choose a compromised node.")
                    return
                msg, det, who = act_exfiltrate(self.att, self.dfn, self.nodes, node)
            elif key == "harden":
                node = self.target_a_combo.get()
                if not node:
                    messagebox.showinfo("Target required", "Choose a compromised node.")
                    return
                msg, det, who = act_harden(self.att, node)
            else:
                msg, det, who = f"(unknown attacker action: {key})", False, "attacker"

            self.log_line(f"[ATTACKER] {msg}", tag="attacker", actor="attacker")
            if det:
                self.dfn.monitoring = min(3.0, self.dfn.monitoring + 0.1)
                self.log_line("  -> Detection pulse: Defender monitoring +0.1", tag="system", actor="system")
            self.att_actions_used += 1
            if self.att_actions_used >= self.att.members:
                self.log_line("Attacker reached action limit for this turn.", tag="system", actor="system")
            self.check_end_conditions()
            self.refresh_all()

        else:
            if key == "patch":
                node = self.target_a_combo.get()
                if not node:
                    messagebox.showinfo("Target required", "Pick a target node.")
                    return
                msg, who = def_patch(self.dfn, self.nodes, node)
            elif key == "monitor":
                msg, who = def_monitor(self.dfn)
            elif key == "awareness":
                msg, who = def_awareness(self.dfn)
            elif key == "isolate":
                node = self.target_a_combo.get()
                if not node:
                    messagebox.showinfo("Target required", "Pick a target node.")
                    return
                msg, who = def_isolate(self.dfn, self.nodes, node)
            elif key == "honeypot":
                node = self.target_a_combo.get()
                if not node:
                    messagebox.showinfo("Target required", "Pick a target node.")
                    return
                msg, who = def_honeypot(self.dfn, node)
            elif key == "forensic":
                msg, who = def_forensic(self.dfn, self.att, self.nodes)
            else:
                msg, who = f"(unknown defender action: {key})", "defender"

            self.log_line(f"[DEFENDER] {msg}", tag="defender", actor="defender")
            self.refresh_all()

    def on_op_exfil(self):
        if self.phase != "attacker":
            return
        if not self.att.compromised:
            messagebox.showinfo("No foothold", "No compromised nodes to exfiltrate from.")
            return
        node = self.simple_choice_dialog("Opportunistic Exfiltrate", "Choose node:", sorted(self.att.compromised))
        if not node:
            return
        msg, det, who = act_exfiltrate(self.att, self.dfn, self.nodes, node)
        self.log_line(f"[ATTACKER] {msg}", tag="attacker", actor="attacker")
        if det:
            self.log_line("  -> Detection pulse: Defender monitoring +0.1", tag="system", actor="system")
            self.dfn.monitoring = min(3.0, self.dfn.monitoring + 0.1)
            if messagebox.askyesno("Immediate Forensic?", "Detection occurred. Defender attempt immediate forensic?"):
                fmsg, who2 = def_forensic(self.dfn, self.att, self.nodes)
                self.log_line(f"[DEFENDER] {fmsg}", tag="defender", actor="defender")
        self.check_end_conditions()
        self.refresh_all()

    def on_end_phase(self):
        if self.phase == "attacker":
            self.phase = "defender"
            self.att_actions_used = 0
            self.log_line("---- Defender Phase ----", tag="system", actor="system")
            self.refresh_all()
        else:
            # End defender phase -> next turn
            self.turn += 1
            self.phase = "attacker"
            self.att_actions_used = 0
            self.log_line(f"==== Turn {self.turn} ====", tag="system", actor="system")
            self.check_end_conditions()
            self.refresh_all()

    def on_save_csv(self):
        if not self.log_records:
            messagebox.showinfo("No Data", "There are no log entries to save yet.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV file", "*.csv"), ("All files", "*.*")],
            title="Save Log to CSV",
            initialfile="cyber_game_log.csv"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["turn", "phase", "actor", "message"])
                writer.writeheader()
                writer.writerows(self.log_records)
            messagebox.showinfo("Saved", f"Log saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not save CSV:\n{e}")

    # ---------- End Conditions ----------
    def check_end_conditions(self):
        if self.att.exfiltrated_value >= WIN_EXFIL:
            self.refresh_all()
            messagebox.showinfo("Game Over", "Attacker reached exfiltration goal.\nATTACKER WINS.")
            self.disable_all()
            return

        if self.turn >= TURN_LIMIT:
            self.refresh_all()
            if self.att.exfiltrated_value >= 50:
                messagebox.showinfo("Time Up", "Significant exfiltration occurred.\nATTACKER wins by damage.")
            else:
                messagebox.showinfo("Time Up", "Damage contained.\nDEFENDER wins.")
            self.disable_all()
            return

        if len(self.att.compromised) == 0 and self.turn >= 5 and self.att.exfiltrated_value < 20:
            self.refresh_all()
            messagebox.showinfo("Containment", "No active footholds and limited damage.\nDEFENDER wins by containment.")
            self.disable_all()

    def disable_all(self):
        self.execute_btn.state(["disabled"])
        self.end_phase_btn.state(["disabled"])
        self.op_exfil_btn.state(["disabled"])
        self.action_combo.state(["disabled"])
        self.target_a_combo.state(["disabled"])
        self.target_b_combo.state(["disabled"])
        self.save_csv_btn.state(["!disabled"])  # allow saving even after game end

    # ---------- Helpers ----------
    def simple_choice_dialog(self, title, prompt, options):
        if not options:
            return None
        win = tk.Toplevel(self)
        win.title(title)
        win.transient(self)
        win.grab_set()
        ttk.Label(win, text=prompt, padding=8).pack(anchor="w")
        var = tk.StringVar(value=options[0])
        cmb = ttk.Combobox(win, textvariable=var, values=options, state="readonly", width=30)
        cmb.pack(padx=8, pady=6)

        chosen = {"value": None}
        def ok():
            chosen["value"] = var.get()
            win.destroy()
        def cancel():
            chosen["value"] = None
            win.destroy()

        btns = ttk.Frame(win)
        btns.pack(pady=8)
        ttk.Button(btns, text="OK", command=ok).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Cancel", command=cancel).pack(side=tk.LEFT, padx=6)
        self.wait_window(win)
        return chosen["value"]

# ======= Main =======
if __name__ == "__main__":
    app = GameApp()
    app.log_line("Safe, abstract simulation. No real-world exploit steps are modeled.", tag="system")
    app.mainloop()
