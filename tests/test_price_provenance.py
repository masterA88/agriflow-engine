"""
Provenance carried by the get_price bot tool (_price_lookup_payload).

Why this file exists. On 2026-09-12 a real WhatsApp question in Javanese,
"Regane bawang abang ing nganjuk pinten?", came back as "rega bawang abang
ing Nganjuk tetep Rp24.375 per kg ... basis data neraca pangan, dudu rega
pasar ing dina iki". The number was right. The year was missing, and it was
missing because the payload said so: _meta_payload() nests
bps_reference_year under "data_as_of", while _price_lookup_payload read it
at the top level. The lookup returned None, so every get_price call shipped

    "price_reference_year": null
    "note_for_model": "Angka ini berasal dari neraca BPS tahun None ...
                       Sebutkan tahunnya saat mengutip angka ini"

which orders the model to state a year it was never given. The guardrail
written to stop a 2022 balance figure being read as today's market price was
itself silent, and nothing in the suite noticed: no test touched this payload.

The gap matters in money terms. The docstring in server.py already records
that cabai rawit is Rp30.750 in the 2022 balance and around Rp58.000 in the
2026 daily series, so a mislabelled year is close to a factor of two.

These tests run against the real artefacts, not fixtures, because the bug was
in how two real functions agreed about a key name. A fixture would have
mirrored my own mistake back at me.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("MOCK_MODE", "false")

from whatsapp_bot import server  # noqa: E402

NGANJUK = "Nganjuk"
BAWANG_MERAH = "bawang_merah"


@pytest.fixture(scope="module")
def nganjuk_bawang_merah():
    return server._price_lookup_payload(BAWANG_MERAH, NGANJUK)


class TestReferenceYearReachesTheModel:
    """The regression itself: the year must survive the lookup."""

    def test_reference_year_is_not_none(self, nganjuk_bawang_merah):
        assert nganjuk_bawang_merah["price_reference_year"] is not None

    def test_reference_year_matches_the_module_constant(self, nganjuk_bawang_merah):
        assert nganjuk_bawang_merah["price_reference_year"] == server.BPS_REFERENCE_YEAR

    def test_note_never_says_none(self, nganjuk_bawang_merah):
        """The exact string the broken build emitted."""
        assert "None" not in nganjuk_bawang_merah["note_for_model"]

    def test_note_states_the_year_it_tells_the_model_to_state(self, nganjuk_bawang_merah):
        assert str(server.BPS_REFERENCE_YEAR) in nganjuk_bawang_merah["note_for_model"]

    def test_meta_payload_still_nests_the_key_where_the_reader_looks(self):
        """Locks the agreement between the two functions, in both directions.

        If _meta_payload is ever flattened, this fails and points at the
        reader rather than letting it silently return None again.
        """
        as_of = server._meta_payload()["data_as_of"]
        assert as_of["bps_reference_year"] == server.BPS_REFERENCE_YEAR


class TestPriceBasisIsHonest:
    """The other half of provenance: which side of the balance the price is."""

    def test_nganjuk_is_surplus_for_shallots(self, nganjuk_bawang_merah):
        """H6 in test_real_surplus_deficit_horti_2022: Nganjuk is Jatim's top
        shallot producer, so its quoted price is a PRODUCER price."""
        assert nganjuk_bawang_merah["role"] == "surplus"

    def test_price_matches_the_answer_given_on_whatsapp(self, nganjuk_bawang_merah):
        """Rp24.375/kg is what the live bot quoted. Locking it means a data
        refresh that moves the number cannot pass unnoticed."""
        assert nganjuk_bawang_merah["price_per_kg"] == 24375.0

    def test_price_basis_names_both_sides(self, nganjuk_bawang_merah):
        basis = nganjuk_bawang_merah["price_basis"]
        assert "produsen" in basis and "konsumen" in basis

    def test_note_forbids_dates_from_other_tools(self, nganjuk_bawang_merah):
        """The failure this note exists to prevent is the model attaching
        get_data_freshness's recent price_history_end to a 2022 figure."""
        note = nganjuk_bawang_merah["note_for_model"]
        assert "BUKAN harga pasar hari ini" in note
        assert "get_price_history" in note


class TestProvenanceIsUniversal:
    """Every commodity and both roles, not just the one that was reported."""

    def test_every_commodity_with_a_nganjuk_row_carries_the_year(self):
        data = server._ensure_engine()
        diperiksa = 0
        for code in data.komoditas:
            try:
                row = server._price_lookup_payload(code, NGANJUK)
            except (server.ToolLookupError, Exception):
                continue
            assert row["price_reference_year"] == server.BPS_REFERENCE_YEAR, code
            assert "None" not in row["note_for_model"], code
            diperiksa += 1
        assert diperiksa >= 2, "terlalu sedikit baris diperiksa untuk bermakna"

    def test_deficit_side_carries_it_too(self):
        """Nganjuk is deficit for garlic, so this exercises the other branch."""
        row = server._price_lookup_payload("bawang_putih", NGANJUK)
        assert row["role"] == "deficit"
        assert row["price_reference_year"] == server.BPS_REFERENCE_YEAR
