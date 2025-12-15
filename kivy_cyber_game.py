# kivy_cyber_game.py
#
# Kivy GUI version of the Cyberattack & Defense Turn-Based Network Simulation.
# Educational, abstract – no real exploit details. For training and teaching only.

from __future__ import annotations

import csv
import random
from collections import defaultdict
from dataclasses import dataclass, field

from kivy.app import App
from kivy.lang import Builder
from kivy.properties import StringProperty, NumericProperty, ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.clock import mainthread

# ===================== GAME CONFIG =====================

TOPOLOGY = {
    "Internet": ["Firewall"],
    "Firewall": ["Internet", "DMZ"],
    "DMZ": ["Firewall", "CorpLAN"],
    "CorpLAN": ["DMZ", "Admin", "Insider", "SIEM"],
    "Admin": ["CorpLAN"],
    "SIEM": ["CorpLAN"],
    "Insider": ["CorpLAN"],
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
    ("honeypot", "Deploy a decoy (narrative/house-rule use)"),
    ("forensic", "Attempt to evict attacker from compromised nodes"),
]


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


@dataclass
class Attacker:
    funds: int = 50
    skill: float = 5.0
    influence: float = 1.0
    members: int = 1
    compromised: set = field(default_factory=set)
    exfiltrated_value: int = 0


@dataclass
class Defender:
    budget: int = 60
    patch_level: dict = field(default_factory=lambda: defaultdict(lambda: 0))
    monitoring: float = 1.0
    awareness: float = 1.0
    isolated: set = field(default_factory=set)
    honeypots: set = field(default_factory=set)


# ===================== ATTACKER ACTIONS =====================

def act_recon(att, dfn, nodes, node):
    base = 0.6
    succ, p, _ = chance_success(base, att.skill, dfn.patch_level[node], 1.0)
    det, dp, _ = detection_check(0.05, dfn.monitoring, 0.8)
    if succ:
        nodes[node]["exposure"] = min(1.0, nodes[node]["exposure"] + 0.1)
    msg = f"Recon {node} -> success={succ} (p={p:.2f}), detected={det} (p={dp:.2f})"
    return msg, det, "attacker"


def act_social(att, dfn, nodes, node="Insider"):
    base = 0.35 * att.influence
    succ, p, _ = chance_success(base, att.skill, dfn.patch_level[node], modifiers=1.0 / dfn.awareness)
    det, dp, _ = detection_check(0.15, dfn.monitoring, 1.2)
    if succ:
        nodes[node]["is_compromised"] = True
        att.compromised.add(node)
    msg = f"Social influence {node} -> success={succ} (p={p:.2f}), detected={det} (p={dp:.2f})"
    return msg, det, "attacker"


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
    base = nodes[target]["exposure"]
    adj_comp = any(adj in att.compromised for adj in TOPOLOGY.get(target, []))
    mod = 1.3 if adj_comp else 1.0
    succ, p, _ = chance_success(base, att.skill, dfn.patch_level[target], mod)
    det, dp, _ = detection_check(0.1 + nodes[target]["value"] / 100.0, dfn.monitoring, 0.9)
    if succ:
        nodes[target]["is_compromised"] = True
        att.compromised.add(target)
    msg = (
        f"Exploit {target} -> success={succ} (p={p:.2f}), detected={det} "
        f"(p={dp:.2f}), adj_comp={adj_comp}"
    )
    return msg, det, "attacker"


def act_lateral(att, dfn, nodes, src, dst):
    if src not in att.compromised:
        return f"Lateral {src}->{dst} -> failed (source not compromised)", False, "attacker"
    if dst not in TOPOLOGY.get(src, []):
        return f"Lateral {src}->{dst} -> failed (not adjacent)", False, "attacker"
    base = 0.4 + (nodes[dst]["exposure"] * 0.3)
    succ, p, _ = chance_success(base, att.skill, dfn.patch_level[dst], 1.0)
    det, dp, _ = detection_check(0.12, dfn.monitoring, 1.0)
    if succ:
        nodes[dst]["is_compromised"] = True
        att.compromised.add(dst)
    msg = f"Lateral {src}->{dst} -> success={succ} (p={p:.2f}), detected={det} (p={dp:.2f})"
    return msg, det, "attacker"


def act_exfiltrate(att, dfn, nodes, node):
    if node not in att.compromised:
        return f"Exfiltrate {node} -> failed (not compromised)", False, "attacker"
    succ, p, _ = chance_success(0.5, att.skill, dfn.patch_level[node], 1.0)
    det, dp, _ = detection_check(0.25 + nodes[node]["value"] / 100.0, dfn.monitoring, 1.0)
    gained = int(nodes[node]["value"] * random.uniform(0.5, 1.0)) if succ else 0
    if succ:
        att.exfiltrated_value += gained
        att.funds += int(gained * 0.5)
    msg = f"Exfiltrate {node} -> success={succ} (p={p:.2f}), detected={det} (p={dp:.2f}), gained={gained}"
    return msg, det, "attacker"


def act_harden(att, node):
    if node not in att.compromised:
        return f"Harden {node} -> failed (not compromised)", False, "attacker"
    att.skill += 0.2
    return "Harden {0} -> persistence improved slightly (skill+0.2)".format(node), False, "attacker"


# ===================== DEFENDER ACTIONS =====================

def def_patch(dfn, nodes, node):
    cost = 8
    if dfn.budget < cost:
        return "Patch -> failed (insufficient budget)", "defender"
    dfn.budget -= cost
    dfn.patch_level[node] = min(10, dfn.patch_level[node] + 2)
    nodes[node]["exposure"] = max(0.05, nodes[node]["exposure"] - 0.15)
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
    if nodes[node]["is_compromised"]:
        nodes[node]["is_compromised"] = False
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
            nodes[node]["is_compromised"] = False
            att.compromised.discard(node)
            removed.append(node)
        att.funds = max(0, att.funds - 10)
        att.skill = max(1.0, att.skill - 0.5)
        return f"Forensic -> success (evicted {removed}, attacker -10 funds, -0.5 skill)", "defender"
    return "Forensic -> no conclusive findings", "defender"


# ===================== KIVY UI =====================

KV = r"""
<GameRoot>:
    orientation: "vertical"
    padding: "8dp"
    spacing: "8dp"

    BoxLayout:
        size_hint_y: None
        height: "40dp"
        spacing: "8dp"
        Label:
            id: turn_label
            text: root.turn_text
            bold: True
        Label:
            id: att_label
            text: root.att_status_text
        Label:
            id: dfn_label
            text: root.dfn_status_text
        Label:
            id: phase_label
            text: root.phase_text
            color: (0.6, 0.1, 0.1, 1) if root.phase == "attacker" else (0.1, 0.3, 0.6, 1)
            bold: True

    BoxLayout:
        size_hint_y: 0.55
        spacing: "8dp"

        # Left side: Nodes table
        BoxLayout:
            orientation: "vertical"
            Label:
                text: "Network Nodes"
                size_hint_y: None
                height: "28dp"
                bold: True

            GridLayout:
                size_hint_y: None
                height: "28dp"
                cols: 6
                padding: "2dp"
                spacing: "2dp"
                canvas.before:
                    Color:
                        rgba: (0.9, 0.9, 0.9, 1)
                    Rectangle:
                        pos: self.pos
                        size: self.size
                Label:
                    text: "Node"
                    bold: True
                Label:
                    text: "Value"
                    bold: True
                Label:
                    text: "Exposure"
                    bold: True
                Label:
                    text: "Compromised"
                    bold: True
                Label:
                    text: "Isolated"
                    bold: True
                Label:
                    text: "Patch"
                    bold: True

            ScrollView:
                bar_width: "8dp"
                GridLayout:
                    id: nodes_grid
                    cols: 6
                    size_hint_y: None
                    height: self.minimum_height
                    row_default_height: "24dp"
                    row_force_default: True
                    spacing: "2dp"
                    padding: "2dp"

        # Right side: Actions
        BoxLayout:
            orientation: "vertical"
            spacing: "4dp"

            Label:
                text: "Actions"
                size_hint_y: None
                height: "28dp"
                bold: True

            BoxLayout:
                size_hint_y: None
                height: "34dp"
                spacing: "4dp"
                Label:
                    text: "Action:"
                    size_hint_x: 0.35
                Spinner:
                    id: action_spinner
                    size_hint_x: 0.65
                    text: "Select..."
                    values: root.action_values
                    on_text: root.on_action_selected(self.text)

            BoxLayout:
                size_hint_y: None
                height: "34dp"
                spacing: "4dp"
                Label:
                    id: target_a_label
                    text: root.target_a_label_text
                    size_hint_x: 0.35
                Spinner:
                    id: target_a_spinner
                    size_hint_x: 0.65
                    text: "Target"
                    values: root.target_a_values
                    on_text: root.on_target_a_selected(self.text)

            BoxLayout:
                size_hint_y: None
                height: "34dp"
                spacing: "4dp"
                Label:
                    id: target_b_label
                    text: root.target_b_label_text
                    size_hint_x: 0.35
                Spinner:
                    id: target_b_spinner
                    size_hint_x: 0.65
                    text: "Destination"
                    values: root.target_b_values

            BoxLayout:
                size_hint_y: None
                height: "40dp"
                spacing: "4dp"
                Button:
                    text: "Execute Action"
                    on_release: root.on_execute_pressed()
                Button:
                    text: "Opportunistic Exfil"
                    on_release: root.on_op_exfil_pressed()
                Button:
                    text: "End Phase"
                    on_release: root.on_end_phase_pressed()

            BoxLayout:
                size_hint_y: None
                height: "34dp"
                spacing: "4dp"
                Label:
                    text: "Op Exfil Node:"
                    size_hint_x: 0.35
                Spinner:
                    id: op_node_spinner
                    size_hint_x: 0.65
                    text: "Compromised node"
                    values: root.op_exfil_values

            BoxLayout:
                size_hint_y: None
                height: "34dp"
                spacing: "4dp"
                Button:
                    text: "Save Log to CSV"
                    on_release: root.on_save_csv_pressed()
                Label:
                    text: root.save_status
                    font_size: "11sp"

    # Log
    BoxLayout:
        orientation: "vertical"
        Label:
            text: "Event Log"
            size_hint_y: None
            height: "24dp"
            bold: True
        ScrollView:
            bar_width: "8dp"
            Label:
                id: log_label
                text: root.log_text
                markup: True
                size_hint_y: None
                height: self.texture_size[1]
                text_size: self.width, None
"""

class GameRoot(BoxLayout):
    turn: int = 1
    phase: str = "attacker"
    att_actions_used: int = 0

    turn_text = StringProperty("")
    att_status_text = StringProperty("")
    dfn_status_text = StringProperty("")
    phase_text = StringProperty("")
    log_text = StringProperty("")
    save_status = StringProperty("")

    action_values = ListProperty([])
    target_a_values = ListProperty([])
    target_b_values = ListProperty([])
    op_exfil_values = ListProperty([])

    target_a_label_text = StringProperty("Target:")
    target_b_label_text = StringProperty("Destination:")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if SEED is not None:
            random.seed(SEED)
        self.nodes = deep_copy_nodes()
        self.att = Attacker()
        self.dfn = Defender()
        self.log_records = []  # for CSV
        self._log_lines = []   # for on-screen log (with markup)
        self.update_all_texts()
        self.refresh_nodes_grid()
        self.refresh_action_spinners()
        self.log_line("[system] Safe, abstract simulation. No real-world exploit steps are modeled.", tag="system")
        self.log_line("[system] ==== Turn 1 ====", tag="system")

    # ---------- UI helpers ----------

    def update_all_texts(self):
        self.turn_text = f"Turn: {self.turn}"
        self.att_status_text = (
            f"Attacker | funds={self.att.funds} "
            f"skill={self.att.skill:.1f} infl={self.att.influence:.2f} "
            f"members={self.att.members} exfil={self.att.exfiltrated_value}"
        )
        self.dfn_status_text = (
            f"Defender | budget={self.dfn.budget} "
            f"monitor={self.dfn.monitoring:.2f} awareness={self.dfn.awareness:.2f}"
        )
        if self.phase == "attacker":
            self.phase_text = f"Phase: Attacker (actions {self.att_actions_used}/{self.att.members})"
        else:
            self.phase_text = "Phase: Defender"

        self.op_exfil_values = sorted(self.att.compromised)

    @mainthread
    def refresh_nodes_grid(self):
        grid = self.ids.nodes_grid
        grid.clear_widgets()
        from kivy.uix.label import Label

        for name in sorted(self.nodes.keys()):
            d = self.nodes[name]
            compromised = d["is_compromised"]
            isolated = name in self.dfn.isolated
            patch = self.dfn.patch_level[name]
            exposure = f"{d['exposure']:.2f}"

            # Choose bg color
            if compromised and isolated:
                bg = (1.0, 0.84, 0.84, 1)  # both
            elif compromised:
                bg = (1.0, 0.90, 0.90, 1)
            elif isolated:
                bg = (1.0, 0.96, 0.87, 1)
            else:
                bg = (1, 1, 1, 1)

            for text in (name, str(d["value"]), exposure,
                         "Yes" if compromised else "No",
                         "Yes" if isolated else "No",
                         str(patch)):
                lbl = Label(text=text)
                with lbl.canvas.before:
                    from kivy.graphics import Color, Rectangle
                    Color(*bg)
                    lbl._rect = Rectangle(pos=lbl.pos, size=lbl.size)
                    lbl.bind(pos=lambda inst, val: setattr(inst._rect, "pos", val))
                    lbl.bind(size=lambda inst, val: setattr(inst._rect, "size", val))
                grid.add_widget(lbl)

    def refresh_action_spinners(self):
        if self.phase == "attacker":
            self.action_values = [f"{k} – {desc}" for k, desc in ATTACKER_ACTIONS]
        else:
            self.action_values = [f"{k} – {desc}" for k, desc in DEFENDER_ACTIONS]
        self.target_a_values = []
        self.target_b_values = []
        self.target_a_label_text = "Target:"
        self.target_b_label_text = "Destination:"
        self.ids.action_spinner.text = "Select..."
        self.ids.target_a_spinner.text = "Target"
        self.ids.target_b_spinner.text = "Destination"

    def on_action_selected(self, text):
        self.target_a_values = []
        self.target_b_values = []
        self.target_a_label_text = "Target:"
        self.target_b_label_text = "Destination:"
        self.ids.target_a_spinner.text = "Target"
        self.ids.target_b_spinner.text = "Destination"

        if not text or "–" not in text:
            return
        key = text.split(" – ")[0]
        if self.phase == "attacker":
            if key in ("recon", "exploit"):
                self.target_a_values = list(self.nodes.keys())
            elif key == "lateral":
                self.target_a_label_text = "From (compromised):"
                self.target_b_label_text = "To (adjacent):"
                self.target_a_values = sorted(self.att.compromised)
            elif key in ("exfiltrate", "harden"):
                self.target_a_values = sorted(self.att.compromised)
        else:
            if key in ("patch", "isolate", "honeypot"):
                self.target_a_values = list(self.nodes.keys())

    def on_target_a_selected(self, text):
        act_text = self.ids.action_spinner.text
        if not act_text or "–" not in act_text:
            return
        key = act_text.split(" – ")[0]
        if self.phase == "attacker" and key == "lateral":
            src = text
            self.target_b_values = TOPOLOGY.get(src, [])

    def log_line(self, text, tag="system", actor=None):
        # colored log with markup
        if tag == "attacker":
            color = "ff0000"
        elif tag == "defender":
            color = "004aad"
        else:
            color = "666666"
        line = f"[color={color}]{text}[/color]"
        self._log_lines.append(line)
        self.log_text = "\n".join(self._log_lines[-500:])  # keep at most 500 lines
        self.log_records.append({
            "turn": self.turn,
            "phase": self.phase,
            "actor": actor if actor else tag,
            "message": text,
        })

    # ---------- Button handlers ----------

    def on_execute_pressed(self):
        act_text = self.ids.action_spinner.text
        if not act_text or "–" not in act_text:
            self.log_line("[system] Please choose an action first.", "system")
            return
        key = act_text.split(" – ")[0]

        if self.phase == "attacker":
            msg, det, actor = self._run_attacker_action(key)
            self.log_line(f"[ATTACKER] {msg}", tag="attacker", actor=actor)
            if det:
                self.dfn.monitoring = min(3.0, self.dfn.monitoring + 0.1)
                self.log_line("  -> Detection pulse: Defender monitoring +0.1", tag="system", actor="system")
            self.att_actions_used += 1
            if self.att_actions_used >= self.att.members:
                self.log_line("Attacker reached action limit for this turn.", "system")
            self.update_all_texts()
            self.refresh_nodes_grid()
            self.check_end_conditions()
        else:
            msg, actor = self._run_defender_action(key)
            self.log_line(f"[DEFENDER] {msg}", tag="defender", actor=actor)
            self.update_all_texts()
            self.refresh_nodes_grid()
            self.check_end_conditions()

    def _run_attacker_action(self, key):
        ta = self.ids.target_a_spinner.text
        tb = self.ids.target_b_spinner.text

        if key == "recruit":
            return act_recruit(self.att)
        if key == "social":
            return act_social(self.att, self.dfn, self.nodes)
        if key == "recon":
            if ta == "Target" or not ta:
                return ("Recon -> target required", False, "attacker")
            return act_recon(self.att, self.dfn, self.nodes, ta)
        if key == "exploit":
            if ta == "Target" or not ta:
                return ("Exploit -> target required", False, "attacker")
            return act_exploit(self.att, self.dfn, self.nodes, ta)
        if key == "lateral":
            if not ta or ta == "Target" or not tb or tb == "Destination":
                return ("Lateral -> source and destination required", False, "attacker")
            return act_lateral(self.att, self.dfn, self.nodes, ta, tb)
        if key == "exfiltrate":
            if ta == "Target" or not ta:
                return ("Exfiltrate -> compromised node required", False, "attacker")
            return act_exfiltrate(self.att, self.dfn, self.nodes, ta)
        if key == "harden":
            if ta == "Target" or not ta:
                return ("Harden -> compromised node required", False, "attacker")
            return act_harden(self.att, ta)
        return (f"(unknown attacker action: {key})", False, "attacker")

    def _run_defender_action(self, key):
        ta = self.ids.target_a_spinner.text
        if key == "patch":
            if ta == "Target" or not ta:
                return "Patch -> target required", "defender"
            return def_patch(self.dfn, self.nodes, ta)
        if key == "monitor":
            return def_monitor(self.dfn)
        if key == "awareness":
            return def_awareness(self.dfn)
        if key == "isolate":
            if ta == "Target" or not ta:
                return "Isolate -> target required", "defender"
            return def_isolate(self.dfn, self.nodes, ta)
        if key == "honeypot":
            if ta == "Target" or not ta:
                return "Honeypot -> target required", "defender"
            return def_honeypot(self.dfn, ta)
        if key == "forensic":
            return def_forensic(self.dfn, self.att, self.nodes)
        return (f"(unknown defender action: {key})", "defender")

    def on_op_exfil_pressed(self):
        if self.phase != "attacker":
            self.log_line("[system] Opportunistic exfil only in attacker phase.", "system")
            return
        if not self.att.compromised:
            self.log_line("[system] No compromised nodes to exfiltrate from.", "system")
            return
        node = self.ids.op_node_spinner.text
        if node in ("Compromised node", "", None):
            self.log_line("[system] Choose a compromised node in the 'Op Exfil Node' spinner.", "system")
            return
        msg, det, actor = act_exfiltrate(self.att, self.dfn, self.nodes, node)
        self.log_line(f"[ATTACKER] {msg}", "attacker", actor="attacker")
        if det:
            self.log_line("  -> Detection pulse: Defender monitoring +0.1", "system", actor="system")
            self.dfn.monitoring = min(3.0, self.dfn.monitoring + 0.1)
            # optional immediate forensic
            msg2, actor2 = def_forensic(self.dfn, self.att, self.nodes)
            self.log_line(f"[DEFENDER] {msg2}", "defender", actor=actor2)
        self.update_all_texts()
        self.refresh_nodes_grid()
        self.check_end_conditions()

    def on_end_phase_pressed(self):
        if self.phase == "attacker":
            # switch to defender phase
            self.phase = "defender"
            self.att_actions_used = 0
            self.log_line("---- Defender Phase ----", "system")
        else:
            # end defender phase -> next turn
            self.turn += 1
            self.phase = "attacker"
            self.att_actions_used = 0
            self.log_line(f"==== Turn {self.turn} ====", "system")
        self.update_all_texts()
        self.refresh_action_spinners()
        self.refresh_nodes_grid()
        self.check_end_conditions()

    def on_save_csv_pressed(self):
        if not self.log_records:
            self.save_status = "No log entries to save."
            return
        filename = "cyber_game_log.csv"
        try:
            with open(filename, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["turn", "phase", "actor", "message"])
                writer.writeheader()
                writer.writerows(self.log_records)
            self.save_status = f"Log saved: {filename}"
        except Exception as e:
            self.save_status = f"Error saving CSV: {e}"

    # ---------- End conditions ----------

    def check_end_conditions(self):
        if self.att.exfiltrated_value >= WIN_EXFIL:
            self.update_all_texts()
            self.log_line("[system] Attacker reached exfiltration goal. ATTACKER WINS.", "system")
            self.disable_game()
            return

        if self.turn >= TURN_LIMIT:
            self.update_all_texts()
            if self.att.exfiltrated_value >= 50:
                self.log_line("[system] Time up: significant exfiltration. ATTACKER wins by damage.", "system")
            else:
                self.log_line("[system] Time up: damage contained. DEFENDER wins.", "system")
            self.disable_game()
            return

        if len(self.att.compromised) == 0 and self.turn >= 5 and self.att.exfiltrated_value < 20:
            self.update_all_texts()
            self.log_line("[system] Containment achieved: no active footholds, limited damage. DEFENDER WINS.", "system")
            self.disable_game()

    def disable_game(self):
        # Disable execute / phase controls visually (no hard lock, but UX hint)
        self.ids.action_spinner.disabled = True
        self.ids.target_a_spinner.disabled = True
        self.ids.target_b_spinner.disabled = True
        self.ids.op_node_spinner.disabled = True

# ===================== APP =====================

class CyberKivyApp(App):
    def build(self):
        self.title = "Cyber Attack & Defense (Kivy Simulation)"
        Builder.load_string(KV)
        return GameRoot()


if __name__ == "__main__":
    CyberKivyApp().run()
