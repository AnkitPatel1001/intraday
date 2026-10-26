"""Tests for symbol validation and Yahoo mapping."""

import pytest
from app.core.symbols import (
    validate_symbol, is_valid_nse_symbol, is_valid_bse_code,
    to_yahoo_nse, to_yahoo_bse, from_yahoo,
    DEMO_UNIVERSE, NIFTY50, SECTOR_MAP,
)


class TestNseSymbol:
    def test_valid(self):
        assert is_valid_nse_symbol("RELIANCE")
        assert is_valid_nse_symbol("BAJAJ-AUTO")
        assert is_valid_nse_symbol("M&M")
        assert is_valid_nse_symbol("NIFTYBEES")

    def test_invalid(self):
        assert not is_valid_nse_symbol("")
        assert not is_valid_nse_symbol("123")
        assert not is_valid_nse_symbol("A" * 25)
        assert not is_valid_nse_symbol("REL IANCE")  # internal space


class TestValidateSymbol:
    def test_valid(self):
        assert validate_symbol("RELIANCE") == "RELIANCE"

    def test_strips_yahoo_suffix(self):
        assert validate_symbol("RELIANCE.NS") == "RELIANCE"
        assert validate_symbol("RELIANCE.BO") == "RELIANCE"

    def test_uppercases(self):
        assert validate_symbol("reliance") == "RELIANCE"

    def test_strips_whitespace(self):
        assert validate_symbol("  RELIANCE  ") == "RELIANCE"

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            validate_symbol("")
        with pytest.raises(ValueError):
            validate_symbol("!!!")

    def test_hyphen(self):
        assert validate_symbol("BAJAJ-AUTO") == "BAJAJ-AUTO"

    def test_ampersand(self):
        assert validate_symbol("M&M") == "M&M"


class TestBseCode:
    def test_valid(self):
        assert is_valid_bse_code("500325")

    def test_invalid(self):
        assert not is_valid_bse_code("50032")
        assert not is_valid_bse_code("ABCDEF")


class TestYahooMapping:
    def test_to_yahoo_nse(self):
        assert to_yahoo_nse("RELIANCE") == "RELIANCE.NS"

    def test_to_yahoo_bse(self):
        assert to_yahoo_bse("RELIANCE") == "RELIANCE.BO"

    def test_from_yahoo_ns(self):
        assert from_yahoo("RELIANCE.NS") == ("RELIANCE", "NSE")

    def test_from_yahoo_bo(self):
        assert from_yahoo("RELIANCE.BO") == ("RELIANCE", "BSE")


class TestUniverse:
    def test_demo_universe_nonempty(self):
        assert len(DEMO_UNIVERSE) >= 40

    def test_universe_symbols_valid(self):
        for sym in DEMO_UNIVERSE:
            assert is_valid_nse_symbol(sym), f"invalid: {sym}"

    def test_nifty50_count(self):
        assert len(NIFTY50) == 50

    def test_sector_map(self):
        assert "RELIANCE" in SECTOR_MAP
        assert "TCS" in SECTOR_MAP
