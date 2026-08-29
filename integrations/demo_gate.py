"""End-to-end sponsor story, runnable offline.

    python -m integrations.demo_gate

An agent tries to run a Foxit document tool on a hostile contract -> Verso
refuses at the gate (exit 2, receipt written). It then reads a clean contract ->
released -> Nutrient DWS extracts the fields. The firewall sits at ingestion, in
front of both.
"""

from __future__ import annotations

from pathlib import Path

from .foxit_gate import QuarantineError, guarded_invoke
from .nutrient_dws import extract_released

HOSTILE = "corpus/build/attacks/A1-01.pdf"
CLEAN = "corpus/build/clean/clean_lease.pdf"


def _line(c: str = "-") -> None:
    print(c * 68)


def main() -> None:
    _line("=")
    print("1. Agent asks the Foxit MCP server to extract text from a contract.")
    _line()
    try:
        out = guarded_invoke("extract_text", HOSTILE, ledger_dir="receipts/foxit")
        print("   tool ran:", out)
    except QuarantineError as e:
        f = e.result.high_findings[0]
        print(f"   REFUSED at the gate — {e.result.filename} is quarantined.")
        print(f"   {f.rule} on page {f.page + 1}: “{f.excerpt}”")
        if e.receipt:
            print(f"   receipt {e.receipt['id']} written (class {e.receipt['class']}).")
        print("   The Foxit tool was never invoked on these bytes.")

    print()
    _line("=")
    print("2. Agent reads a clean contract; Nutrient DWS extracts on release.")
    _line()
    outcome = extract_released(CLEAN)
    if outcome.released:
        print("   released. DWS extraction:")
        for field in outcome.extraction["fields"]:
            print(f"     {field['name']:24} = {field['value']:12} "
                  f"(conf {field['confidence']})")
    else:
        print("   quarantined; findings handed to the DWS Viewer for review.")
    _line("=")


if __name__ == "__main__":
    main()
