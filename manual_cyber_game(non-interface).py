"""
Manual turn-based Attacker vs Defender simulation (educational & safe).
- You choose actions for both sides each turn.
- No real-world exploit instructions: everything is abstracted into probabilities & resources.

Run: python manual_cyber_game(non-interface).py
"""

import random
from collections import defaultdict

# ===== Config / Topology =====
TOPOLOGY = {
    "Internet": ["Firewall"],
    "Firewall": ["Internet", "DMZ"],
    "DMZ": ["Firewall", "CorpLAN"],
    "CorpLAN": ["DMZ", "Admin", "Insider", "SIEM"],
    "Admin": ["CorpLAN"],
    "SIEM": ["CorpLAN"],
    "Insider": ["CorpLAN"]
}

# Node attributes (value = payoff if data is exfiltrated; exposure = ease to attack)
BASE_NODES = {
    "Internet": {"value": 0,  "exposure": 1.00, "is_compromised": False},
    "Firewall": {"value": 5,  "exposure": 0.20, "is_compromised": False},
    "DMZ":      {"value": 10, "exposure": 0.40, "is_compromised": False},
    "CorpLAN":  {"value": 20, "exposure": 0.60, "is_compromised": False},
    "Admin":    {"value": 30, "exposure": 0.30, "is_compromised": False},
    "SIEM":     {"value": 15, "exposure": 0.25, "is_compromised": False},
    "Insider":  {"value": 8,  "exposure": 0.50, "is_compromised": False},
}

WIN_EXFIL = 100     # Attacker wins if this exfil value reached before turn limit
TURNS = 14          # Game length before "defender points" check
SEED = 42           # Change to vary runs; or set to None for full randomness

# ===== Utility =====
def deep_copy_nodes():
    return {k: v.copy() for k, v in BASE_NODES.items()}

def pretty_nodes(nodes):
    lines = []
    for n in sorted(nodes.keys()):
        d = nodes[n]
        lines.append(f"  {n:8} | value={d['value']:>2} | exp={d['exposure']:.2f} | compromised={d['is_compromised']}")
    return "\n".join(lines)

def input_choice(prompt, choices):
    choices_lower = {c.lower(): c for c in choices}
    while True:
        raw = input(prompt).strip()
        if raw.lower() in choices_lower:
            return choices_lower[raw.lower()]
        print(f"  Invalid choice. Options: {', '.join(choices)}")

def input_target(prompt, valid_targets):
    vset = set(valid_targets)
    while True:
        raw = input(prompt + " ").strip()
        if raw == "?":
            print("  Valid targets:", ", ".join(valid_targets))
            continue
        if raw in vset:
            return raw
        print("  Invalid target. Type '?' to list valid targets.")

def ask_yes_no(prompt, default="y"):
    while True:
        ans = input(f"{prompt} (y/n) [{default}] ").strip().lower()
        if ans == "": ans = default
        if ans in ("y","n"):
            return ans == "y"
        print("  Please enter 'y' or 'n'.")

# ===== Game State =====
class Attacker:
    def __init__(self):
        self.funds = 50
        self.skill = 5.0
        self.influence = 1.0
        self.members = 1
        self.compromised = set()
        self.exfiltrated_value = 0

    def status(self):
        return (f"Attacker => funds={self.funds}, skill={self.skill:.1f}, "
                f"influence={self.influence:.2f}, members={self.members}, "
                f"exfil={self.exfiltrated_value}")

class Defender:
    def __init__(self):
        self.budget = 60
        self.patch_level = defaultdict(lambda: 0)  # 0..10
        self.monitoring = 1.0
        self.awareness = 1.0
        self.isolated = set()
        self.honeypots = set()

    def status(self):
        return (f"Defender => budget={self.budget}, monitoring={self.monitoring:.2f}, "
                f"awareness={self.awareness:.2f}, isolated={list(self.isolated) or '[]'}")

# ===== Probabilities =====
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

# ===== Attacker Actions =====
def act_recon(att, dfn, nodes, node):
    base = 0.6
    succ, p, r = chance_success(base, att.skill, dfn.patch_level[node], 1.0)
    det, dp, dr = detection_check(0.05, dfn.monitoring, 0.8)
    if succ:
        nodes[node]['exposure'] = min(1.0, nodes[node]['exposure'] + 0.1)
    return f"Recon {node} -> success={succ} (p={p:.2f}), detected={det} (p={dp:.2f})", det

def act_social(att, dfn, nodes, node="Insider"):
    base = 0.35 * att.influence
    succ, p, r = chance_success(base, att.skill, dfn.patch_level[node], modifiers=1.0/dfn.awareness)
    det, dp, dr = detection_check(0.15, dfn.monitoring, 1.2)
    if succ:
        nodes[node]['is_compromised'] = True
        att.compromised.add(node)
    return f"Social influence {node} -> success={succ} (p={p:.2f}), detected={det} (p={dp:.2f})", det

def act_recruit(att):
    cost = 15
    if att.funds >= cost:
        att.funds -= cost
        att.members += 1
        att.skill += 1.0
        return "Recruit -> success (members+1, skill+1)", False
    return "Recruit -> failed (insufficient funds)", False

def act_exploit(att, dfn, nodes, target):
    if target in dfn.isolated:
        return f"Exploit {target} -> aborted (isolated)", False
    base = nodes[target]['exposure']
    adj_compromised = any(adj in att.compromised for adj in TOPOLOGY.get(target, []))
    mod = 1.3 if adj_compromised else 1.0
    succ, p, r = chance_success(base, att.skill, dfn.patch_level[target], mod)
    det, dp, dr = detection_check(0.1 + nodes[target]['value']/100.0, dfn.monitoring, 0.9)
    if succ:
        nodes[target]['is_compromised'] = True
        att.compromised.add(target)
    return (f"Exploit {target} -> success={succ} (p={p:.2f}), detected={det} "
            f"(p={dp:.2f}), adj_comp={adj_compromised}"), det

def act_lateral(att, dfn, nodes, src, dst):
    if src not in att.compromised:
        return f"Lateral {src}->{dst} -> failed (source not compromised)", False
    if dst not in TOPOLOGY.get(src, []):
        return f"Lateral {src}->{dst} -> failed (not adjacent)", False
    base = 0.4 + (nodes[dst]['exposure'] * 0.3)
    succ, p, r = chance_success(base, att.skill, dfn.patch_level[dst], 1.0)
    det, dp, dr = detection_check(0.12, dfn.monitoring, 1.0)
    if succ:
        nodes[dst]['is_compromised'] = True
        att.compromised.add(dst)
    return f"Lateral {src}->{dst} -> success={succ} (p={p:.2f}), detected={det} (p={dp:.2f})", det

def act_exfiltrate(att, dfn, nodes, node):
    if node not in att.compromised:
        return f"Exfiltrate {node} -> failed (not compromised)", False
    succ, p, r = chance_success(0.5, att.skill, dfn.patch_level[node], 1.0)
    det, dp, dr = detection_check(0.25 + nodes[node]['value']/100.0, dfn.monitoring, 1.0)
    gained = int(nodes[node]['value'] * random.uniform(0.5, 1.0)) if succ else 0
    if succ:
        att.exfiltrated_value += gained
        att.funds += int(gained * 0.5)
    return f"Exfiltrate {node} -> success={succ} (p={p:.2f}), detected={det} (p={dp:.2f}), gained={gained}", det

def act_harden(att, node):
    if node not in att.compromised:
        return f"Harden {node} -> failed (not compromised)", False
    att.skill += 0.2
    return f"Harden {node} -> persistence improved slightly (skill+0.2)", False

# ===== Defender Actions =====
def def_patch(dfn, nodes, node):
    cost = 8
    if dfn.budget < cost:
        return "Patch -> failed (insufficient budget)"
    dfn.budget -= cost
    dfn.patch_level[node] = min(10, dfn.patch_level[node] + 2)
    nodes[node]['exposure'] = max(0.05, nodes[node]['exposure'] - 0.15)
    return f"Patch {node} -> success (patch={dfn.patch_level[node]}, exposure={nodes[node]['exposure']:.2f})"

def def_monitor(dfn):
    cost = 6
    if dfn.budget < cost:
        return "Monitoring -> failed (insufficient budget)"
    dfn.budget -= cost
    dfn.monitoring = min(3.0, dfn.monitoring + 0.3)
    return f"Monitoring -> increased (now {dfn.monitoring:.2f})"

def def_awareness(dfn):
    cost = 10
    if dfn.budget < cost:
        return "Awareness -> failed (insufficient budget)"
    dfn.budget -= cost
    dfn.awareness = max(0.5, dfn.awareness - 0.2)
    return f"Awareness -> campaign run (awareness now {dfn.awareness:.2f})"

def def_isolate(dfn, nodes, node):
    cost = 12
    if dfn.budget < cost:
        return "Isolate -> failed (insufficient budget)"
    dfn.budget -= cost
    dfn.isolated.add(node)
    if nodes[node]['is_compromised']:
        nodes[node]['is_compromised'] = False
    return f"Isolate {node} -> success (segment cut; compromise removed if present)"

def def_honeypot(dfn, node):
    cost = 7
    if dfn.budget < cost:
        return "Honeypot -> failed (insufficient budget)"
    dfn.budget -= cost
    dfn.honeypots.add(node)
    return f"Honeypot near {node} -> deployed"

def def_forensic(dfn, att, nodes):
    cost = 10
    if dfn.budget < cost:
        return "Forensic -> failed (insufficient budget)"
    dfn.budget -= cost
    compromised_count = len(att.compromised)
    base = 0.4 + 0.05 * compromised_count
    p = min(0.9, base * dfn.monitoring)
    succ = random.random() < p
    if succ and compromised_count:
        # remove roughly half (rounded up)
        rem_ct = max(1, compromised_count // 2)
        removed = []
        for node in list(att.compromised)[:rem_ct]:
            nodes[node]['is_compromised'] = False
            att.compromised.discard(node)
            removed.append(node)
        att.funds = max(0, att.funds - 10)
        att.skill = max(1.0, att.skill - 0.5)
        return f"Forensic -> success (evicted {removed}, attacker -10 funds, -0.5 skill)"
    return "Forensic -> no conclusive findings"

# ===== Turn Flow =====
ATTACKER_ACTIONS = [
    ("recon", "Pick a node to learn & tilt exposure (+0.10). Low detection."),
    ("social", "Attempt to influence/bride the Insider (awareness reduces success)."),
    ("recruit", "Spend funds to add a member and +1 skill."),
    ("exploit", "Try to compromise a node (easier with adjacent foothold)."),
    ("lateral", "Move from a compromised node to an adjacent node."),
    ("exfiltrate", "Attempt to exfiltrate data from a compromised node."),
    ("harden", "Increase persistence/skill slightly on a compromised node."),
]

DEFENDER_ACTIONS = [
    ("patch", "Reduce exposure & raise patch level on a node."),
    ("monitor", "Increase global detection probability."),
    ("awareness", "Reduce success of social influence attempts."),
    ("isolate", "Cut off a node; remove compromise if present."),
    ("honeypot", "Place a decoy (narrative effect; use for RP or house rules)."),
    ("forensic", "Attempt to evict attacker from compromised nodes."),
]

def choose_attacker_actions(att, dfn, nodes):
    max_actions = att.members
    print(f"\nChoose up to {max_actions} attacker action(s).")
    for i, (k, desc) in enumerate(ATTACKER_ACTIONS, 1):
        print(f"  {i}. {k:10} - {desc}")
    actions = []
    for slot in range(max_actions):
        pick = input(f" Select attacker action #{slot+1} (1-{len(ATTACKER_ACTIONS)} or Enter to stop): ").strip()
        if pick == "":
            break
        if not pick.isdigit() or not (1 <= int(pick) <= len(ATTACKER_ACTIONS)):
            print("  Invalid number.")
            continue
        key = ATTACKER_ACTIONS[int(pick)-1][0]
        target = None
        if key in ("recon","exploit"):
            target = input_target("  Target node (? for list):", list(nodes.keys()))
        elif key == "lateral":
            if not att.compromised:
                print("  You have no compromised nodes to move from.")
                continue
            src = input_target("  Source (compromised) node (? for list):", sorted(att.compromised))
            dst = input_target(f"  Destination adjacent to {src} (? for list):", TOPOLOGY.get(src, []))
            target = (src, dst)
        elif key == "exfiltrate":
            if not att.compromised:
                print("  You have no compromised nodes to exfiltrate from.")
                continue
            target = input_target("  From which compromised node (? for list):", sorted(att.compromised))
        elif key == "harden":
            if not att.compromised:
                print("  You have no compromised nodes to harden.")
                continue
            target = input_target("  Harden which compromised node (? for list):", sorted(att.compromised))
        elif key == "social":
            target = "Insider"  # fixed target
        actions.append((key, target))
    return actions

def resolve_attacker_action(key, target, att, dfn, nodes):
    if key == "recon":
        msg, det = act_recon(att, dfn, nodes, target)
    elif key == "social":
        msg, det = act_social(att, dfn, nodes)
    elif key == "recruit":
        msg, det = act_recruit(att)
    elif key == "exploit":
        msg, det = act_exploit(att, dfn, nodes, target)
    elif key == "lateral":
        src, dst = target
        msg, det = act_lateral(att, dfn, nodes, src, dst)
    elif key == "exfiltrate":
        msg, det = act_exfiltrate(att, dfn, nodes, target)
    elif key == "harden":
        msg, det = act_harden(att, target)
    else:
        msg, det = f"(unknown attacker action: {key})", False
    print("  [ATTACKER]", msg)
    if det:
        dfn.monitoring = min(3.0, dfn.monitoring + 0.1)
        print("    -> Detection pulse! Defender monitoring +0.1")
    return msg

def choose_defender_actions(att, dfn, nodes):
    # Defender gets 1 action per turn by default; optional second if budget >= 20 (house rule).
    bonus = 1 if dfn.budget >= 20 and ask_yes_no("Defender: take a second action this turn?") else 0
    max_actions = 1 + bonus
    print(f"\nChoose up to {max_actions} defender action(s).")
    for i, (k, desc) in enumerate(DEFENDER_ACTIONS, 1):
        print(f"  {i}. {k:10} - {desc}")
    actions = []
    for slot in range(max_actions):
        pick = input(f" Select defender action #{slot+1} (1-{len(DEFENDER_ACTIONS)} or Enter to stop): ").strip()
        if pick == "":
            break
        if not pick.isdigit() or not (1 <= int(pick) <= len(DEFENDER_ACTIONS)):
            print("  Invalid number.")
            continue
        key = DEFENDER_ACTIONS[int(pick)-1][0]
        target = None
        if key in ("patch","isolate","honeypot"):
            target = input_target("  Target node (? for list):", list(nodes.keys()))
        actions.append((key, target))
    return actions

def resolve_defender_action(key, target, att, dfn, nodes):
    if key == "patch":
        msg = def_patch(dfn, nodes, target)
    elif key == "monitor":
        msg = def_monitor(dfn)
    elif key == "awareness":
        msg = def_awareness(dfn)
    elif key == "isolate":
        msg = def_isolate(dfn, nodes, target)
    elif key == "honeypot":
        msg = def_honeypot(dfn, target)
    elif key == "forensic":
        msg = def_forensic(dfn, att, nodes)
    else:
        msg = f"(unknown defender action: {key})"
    print("  [DEFENDER]", msg)
    return msg

# ===== Game Loop =====
def print_header(turn, att, dfn, nodes):
    print("\n" + "="*72)
    print(f"TURN {turn}")
    print("-"*72)
    print(att.status())
    print(dfn.status())
    print("Compromised nodes:", sorted(att.compromised) or "None")
    print("Nodes:")
    print(pretty_nodes(nodes))
    print("-"*72)

def check_end(att, turn):
    if att.exfiltrated_value >= WIN_EXFIL:
        print("\n*** Attacker achieved exfiltration goal! ATTACKER WINS. ***")
        return True
    if turn >= TURNS:
        if att.exfiltrated_value >= 50:
            print("\nTime limit reached: significant exfiltration occurred.")
            print("*** ATTACKER wins by damage ***")
        else:
            print("\nTime limit reached: damage contained.")
            print("*** DEFENDER wins ***")
        return True
    return False

def main():
    if SEED is not None:
        random.seed(SEED)
    nodes = deep_copy_nodes()
    att = Attacker()
    dfn = Defender()

    print("\nManual Attacker vs Defender (Educational Simulation)")
    print("Type '?' when prompted for a target to list valid choices.")
    print("Ethical note: This is a safe, abstract simulation for learning defensive strategy.\n")

    for turn in range(1, TURNS+1):
        print_header(turn, att, dfn, nodes)

        # --- Attacker phase ---
        a_actions = choose_attacker_actions(att, dfn, nodes)
        for key, target in a_actions:
            resolve_attacker_action(key, target, att, dfn, nodes)

        # Opportunistic exfil at end of attacker phase (optional)
        if att.compromised and ask_yes_no("Attacker: attempt opportunistic exfiltrate from a compromised node?", default="n"):
            node = input_target("  Node to exfiltrate (? for list):", sorted(att.compromised))
            msg, det = act_exfiltrate(att, dfn, nodes, node)
            print("  [ATTACKER]", msg)
            if det:
                print("    -> Detection pulse! Defender monitoring +0.1")
                dfn.monitoring = min(3.0, dfn.monitoring + 0.1)
                # optional immediate forensic on detection
                if ask_yes_no("Defender: attempt immediate forensic response?", default="y"):
                    print("  [DEFENDER]", def_forensic(dfn, att, nodes))

        if check_end(att, turn):
            break

        # --- Defender phase ---
        d_actions = choose_defender_actions(att, dfn, nodes)
        for key, target in d_actions:
            resolve_defender_action(key, target, att, dfn, nodes)

        # Defender early win condition (steady containment)
        if len(att.compromised) == 0 and turn >= 5 and att.exfiltrated_value < 20:
            print("\nNo active footholds and limited damage for several turns.")
            print("*** DEFENDER wins by containment ***")
            break

        # Optional continue prompt
        if not ask_yes_no("Proceed to next turn?", default="y"):
            print("\nGame aborted by user.")
            break

if __name__ == "__main__":
    main()
