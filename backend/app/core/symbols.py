"""NSE/BSE symbol validation and Yahoo Finance symbol mapping."""

from __future__ import annotations

import re

# NSE equity symbol: 1-20 chars, letters/digits/hyphen/ampersand, no leading/trailing space.
# Examples: RELIANCE, BAJAJ-AUTO, M&M, L&TFH, NIFTYBEES
_NSE_RE = re.compile(r"^[A-Z][A-Z0-9&\-\.]{0,19}$")
# BSE scrip code: 6-digit numeric (e.g. 500325 for Reliance)
_BSE_CODE_RE = re.compile(r"^\d{6}$")
# Yahoo suffix
_NSE_SUFFIX = ".NS"
_BSE_SUFFIX = ".BO"


def is_valid_nse_symbol(sym: str) -> bool:
    return bool(_NSE_RE.match(sym.upper().strip()))


def is_valid_bse_code(code: str) -> bool:
    return bool(_BSE_CODE_RE.match(code.strip()))


def validate_symbol(sym: str) -> str:
    """Normalize and validate an NSE symbol. Raises ValueError if invalid."""
    s = sym.upper().strip()
    if not s:
        raise ValueError("empty symbol")
    # strip Yahoo suffix if user included it
    if s.endswith(_NSE_SUFFIX):
        s = s[: -len(_NSE_SUFFIX)]
    if s.endswith(_BSE_SUFFIX):
        s = s[: -len(_BSE_SUFFIX)]
    if not is_valid_nse_symbol(s):
        raise ValueError(f"invalid NSE symbol: {sym!r}")
    return s


def to_yahoo_nse(sym: str) -> str:
    return validate_symbol(sym) + _NSE_SUFFIX


def to_yahoo_bse(sym_or_code: str) -> str:
    return sym_or_code.strip().upper() + _BSE_SUFFIX


def from_yahoo(yahoo_sym: str) -> tuple[str, str]:
    """Yahoo symbol -> (nse_symbol, exchange). 'RELIANCE.NS' -> ('RELIANCE', 'NSE')."""
    s = yahoo_sym.upper().strip()
    if s.endswith(_NSE_SUFFIX):
        return s[: -len(_NSE_SUFFIX)], "NSE"
    if s.endswith(_BSE_SUFFIX):
        return s[: -len(_BSE_SUFFIX)], "BSE"
    return s, "NSE"


# Well-known NSE symbols for demo/testing. NOT a live universe.
DEMO_UNIVERSE = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "SBIN",
    "BHARTIARTL", "ITC", "KOTAKBANK", "LT", "AXISBANK", "ASIANPAINT",
    "MARUTI", "HINDUNILVR", "BAJFINANCE", "HCLTECH", "WIPRO", "SUNPHARMA",
    "TITAN", "ULTRACEMCO", "NESTLEIND", "NTPC", "POWERGRID", "M&M",
    "TATAMOTORS", "TATASTEEL", "JSWSTEEL", "ADANIENT", "ADANIPORTS", "COALINDIA",
    "BAJAJ-AUTO", "TECHM", "INDUSINDBK", "GRASIM", "HINDALCO", "DRREDDY",
    "CIPLA", "DIVISLAB", "APOLLOHOSP", "BRITANNIA", "EICHERMOT", "HEROMOTOCO",
    "BAJAJFINSV", "BPCL", "ONGC", "SBILIFE", "HDFCLIFE", "TATACONSUM",
    "LTIM", "ADANIGREEN",
]

# Sector mapping for demo dashboard (not authoritative)
SECTOR_MAP = {
    "RELIANCE": "Oil & Gas", "TCS": "IT", "HDFCBANK": "Banking", "ICICIBANK": "Banking",
    "INFY": "IT", "SBIN": "Banking", "BHARTIARTL": "Telecom", "ITC": "FMCG",
    "KOTAKBANK": "Banking", "LT": "Infrastructure", "AXISBANK": "Banking",
    "ASIANPAINT": "FMCG", "MARUTI": "Auto", "HINDUNILVR": "FMCG",
    "BAJFINANCE": "NBFC", "HCLTECH": "IT", "WIPRO": "IT", "SUNPHARMA": "Pharma",
    "TITAN": "Consumer", "ULTRACEMCO": "Cement", "NESTLEIND": "FMCG",
    "NTPC": "Power", "POWERGRID": "Power", "M&M": "Auto", "TATAMOTORS": "Auto",
    "TATASTEEL": "Metals", "JSWSTEEL": "Metals", "COALINDIA": "Mining",
    "BAJAJ-AUTO": "Auto", "TECHM": "IT", "INDUSINDBK": "Banking",
}

# NSE index constituents (simplified, for demo overview)
NIFTY50 = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BHARTIARTL",
    "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "GRASIM",
    "HCLTECH", "HDFCBANK", "HDFCLIFE", "HEROMOTOCO", "HINDALCO",
    "HINDUNILVR", "ICICIBANK", "INDUSINDBK", "INFY", "ITC",
    "JIOFIN", "JSWSTEEL", "KOTAKBANK", "LT", "LTIM",
    "M&M", "MARUTI", "NESTLEIND", "NTPC", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SHRIRAMFIN",
    "SUNPHARMA", "TATACONSUM", "TATAMOTORS", "TATASTEEL", "TCS",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO",
]
