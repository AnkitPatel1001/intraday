"""Automatic buy/sell decisions gated by the Time Machine Monte Carlo verdict.

Paper trading only — this module never touches a live broker. It composes
the existing plan + risk + time-machine engines into a single PASS/BLOCK +
edge-threshold gate: a trade is auto-entered only when the risk check PASSes
AND the Time Machine replay's target-vs-stop edge clears a minimum bar.

"Edge" is the same quantity the time-machine verdict already reports: the
share of target-or-stop replays that hit target first, minus the break-even
share implied by the plan's R multiple (see engine.timemachine.lean). It is
direction-aware — positive always means "favors the target", regardless of
side — so no sign-flipping is needed here for buy vs sell.
"""

from __future__ import annotations

from app.engine.timemachine import lean

# Same bands as the human-readable verdict (engine.timemachine.verdict):
# < 5 points of edge = coin flip, >= 15 points = a strong lean.
EDGE_LEAN = 0.05
EDGE_STRONG = 0.15


def decide_auto_trade(
    mc: dict | None,
    risk_passed: bool,
    min_edge: float = EDGE_LEAN,
    shares: int = 0,
) -> dict:
    """Decide whether a time-machine-checked plan should be auto-entered.

    Returns {"action": "enter" | "skip", "edge": float | None, "reason": str}.
    Never raises — a missing/ambiguous Monte Carlo result is just a reason
    to skip, not an error.
    """
    if shares <= 0:
        return {
            "action": "skip", "edge": None,
            "reason": "position size is zero — capital too small for this risk_pct",
        }
    if not risk_passed:
        return {"action": "skip", "edge": None, "reason": "risk check blocked the trade"}
    if mc is None:
        return {
            "action": "skip", "edge": None,
            "reason": "time machine could not simulate this plan — see time_machine_error",
        }
    lv = lean(mc)
    if lv is None:
        return {
            "action": "skip", "edge": None,
            "reason": "no replay reached target or stop — no edge to act on",
        }
    edge, _share, _even = lv
    edge = round(edge, 4)
    if edge < min_edge:
        return {
            "action": "skip", "edge": edge,
            "reason": (
                f"edge {edge:+.3f} is below the {min_edge:.3f} threshold "
                "— too close to a coin flip (or leans toward the stop)"
            ),
        }
    return {
        "action": "enter", "edge": edge,
        "reason": (
            f"edge {edge:+.3f} at/above the {min_edge:.3f} threshold "
            "— the target leads the stop across the replays"
        ),
    }
