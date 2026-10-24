---
name: risk-manager
description: >-
  Check every trade against user-configured risk limits. PASS or BLOCK with
  reasons. Checks: max loss per trade, daily loss limit, position count,
  minimum risk/reward, entry window, position sizing, stop required.
  Rejects trades when essential data is missing. Use before paper trading
  or any order placement.
argument-hint: "[trade plan or order details]"
---

# risk-manager

Check a trade against risk limits. PASS or BLOCK. No exceptions.

## Checks

| Check | Condition |
|-------|-----------|
| Has entry | entry > 0 |
| Has stop | stop > 0 (if required) |
| Has target | target > 0 |
| Stop sanity | buy: stop < entry; sell: stop > entry |
| Target sanity | buy: target > entry; sell: target < entry |
| Min R:R | reward/risk ≥ minimum |
| Daily loss | daily P&L > -max daily loss |
| Trades/day | count < max per day |
| Positions | open < max positions |
| Entry window | now ≤ no_entries_after |
| Position size | value ≤ max % of capital |

## Output

- `PASS` or `BLOCK`
- List of all checks with pass/fail and detail
- Fingerprint for order matching (prevents TOCTOU)

## Rules

- Missing essential data = automatic BLOCK.
- Fingerprint must match before order can proceed.
- All limits user-configurable.
- Not a recommendation — rules check only.

## Failure Conditions

- Missing entry/stop/target → BLOCK.
- Any limit exceeded → BLOCK with reason.
- Invalid time format → skip window check, warn.
