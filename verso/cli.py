"""verso -- the command-line interface. This is the contract other things gate on.

    verso scan <path>                 exit 0 clean, 2 quarantined, 1 error
    verso scan <path> --json          findings as JSON on stdout
    verso scan <path> --receipt f     emit a signed refusal receipt
    verso scan <path> --overlay f     emit the findings overlay PNG
    verso scan <path> --ledger d      append the receipt to a chained ledger
    verso scan <path> --advisory      run the optional semantic advisory pass
    verso sanitize <path> -o <path>   emit a cleaned copy, refuse if unsafe
    verso ledger verify <dir>         verify receipt chain integrity
    verso keygen                      create the signing keypair

Exit code 2 is the whole product; anything wrapping Verso gates on it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .errors import VersoError
from .scan import EXIT_CLEAN, EXIT_ERROR, EXIT_QUARANTINE, scan
from .serialize import finding_dict

_C = {
    "red": "\033[31m", "green": "\033[32m", "yellow": "\033[33m",
    "bold": "\033[1m", "dim": "\033[2m", "reset": "\033[0m",
}


def _color(s: str, name: str) -> str:
    if not sys.stdout.isatty():
        return s
    return f"{_C[name]}{s}{_C['reset']}"


# --------------------------------------------------------------------------- #
def _print_human(result) -> None:
    sev_color = {"high": "red", "medium": "yellow", "low": "dim"}
    if result.decision == "quarantined":
        head = _color("QUARANTINED", "red")
        verb = "refused"
    else:
        head = _color("CLEAN", "green")
        verb = "released"
    print(f"{_color('verso', 'bold')}  {result.filename}  →  {head}")
    print(_color(f"  sha256 {result.sha256}", "dim"))
    print(_color(f"  {result.n_pages} page(s), {result.size} bytes, "
                 f"{result.revisions} revision(s)", "dim"))

    if result.findings:
        print(f"\n  {len(result.findings)} finding(s):")
        for f in result.findings:
            loc = (f"p{f.page + 1} {f.bbox.as_list()}" if f.bbox
                   else f"p{f.page + 1} (metadata)")
            tag = _color(f"[{f.severity:^6}]", sev_color.get(f.severity, "dim"))
            print(f"    {tag} {_color(f.rule, 'bold')}  {loc}")
            ex = f.excerpt + ("…" if f.excerpt_truncated else "")
            print(_color(f"           “{ex}”", "dim"))
    else:
        print("\n  no structural findings.")

    if result.advisory:
        print(f"\n  {len(result.advisory)} advisory (does not affect the decision):")
        for a in result.advisory:
            print(_color(f"    [A8] p{a['page']}  {a['reason']}", "yellow"))
            print(_color(f"         “{a['excerpt']}”", "dim"))

    print(f"\n  decision: the document was {verb}. exit {result.exit_code}.")


# --------------------------------------------------------------------------- #
def cmd_scan(args) -> int:
    try:
        result = scan(args.path, with_render=not args.no_ocr,
                      with_advisory=args.advisory)
    except VersoError as e:
        print(_color(f"error: {e}", "red"), file=sys.stderr)
        return EXIT_ERROR

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_human(result)

    if args.overlay:
        from .overlay import render_overlay
        out = render_overlay(result, args.overlay)
        if not args.json:
            print(_color(f"  overlay written to {out}", "dim"))

    if (args.receipt or args.ledger) and result.decision == "quarantined":
        from .receipt import (append, build_r3_receipt, latest,
                              load_or_create_keypair)
        private, public = load_or_create_keypair(args.keys)
        prev_id = latest(args.ledger) if args.ledger else None
        receipt = build_r3_receipt(result, private, public,
                                   on_behalf_of=args.on_behalf_of, prev_id=prev_id)
        if args.receipt:
            Path(args.receipt).write_text(
                json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True))
            if not args.json:
                print(_color(f"  receipt {receipt['id']} → {args.receipt}", "dim"))
        if args.ledger:
            p = append(receipt, args.ledger)
            if not args.json:
                print(_color(f"  receipt {receipt['id']} appended → {p}", "dim"))
    elif (args.receipt or args.ledger) and not args.json:
        print(_color("  (no receipt: nothing was refused)", "dim"))

    return result.exit_code


def cmd_sanitize(args) -> int:
    from .sanitize import sanitize
    try:
        res = sanitize(args.path)
    except VersoError as e:
        print(_color(f"error: {e}", "red"), file=sys.stderr)
        return EXIT_ERROR
    if res.safe:
        Path(args.output).write_bytes(res.cleaned_bytes)
        print(_color("sanitized", "green"),
              f"→ {args.output}")
        for r in res.removed:
            print(_color(f"  removed: {r}", "dim"))
        return EXIT_CLEAN
    print(_color("REFUSED", "red"), "— cannot be made safe by metadata cleaning.")
    for r in res.removed:
        print(_color(f"  removed: {r}", "dim"))
    for r in res.remaining:
        print(_color(f"  remains: {r} (in-content attack, not auto-removable)", "yellow"))
    return EXIT_QUARANTINE


def cmd_ledger_verify(args) -> int:
    from .receipt import verify
    res = verify(args.dir)
    if res.ok:
        print(_color("ledger OK", "green"),
              f"— {res.count} receipt(s), chain intact, signatures valid.")
        return EXIT_CLEAN
    print(_color("ledger BROKEN", "red"),
          f"— first break at {res.first_break}: {res.reason}")
    return EXIT_ERROR


def cmd_keygen(args) -> int:
    from .receipt import load_or_create_keypair, public_key_b64
    _priv, pub = load_or_create_keypair(args.keys)
    print(_color("signing key ready", "green"), f"in {args.keys}/")
    print(f"  public key (ed25519): {public_key_b64(pub)}")
    return EXIT_CLEAN


# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="verso",
                                description="A document firewall for AI agents.")
    p.add_argument("--keys", default="keys",
                   help="directory holding the signing keypair (default: keys)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", help="inspect a PDF; exit 2 if quarantined")
    s.add_argument("path")
    s.add_argument("--json", action="store_true", help="emit findings as JSON")
    s.add_argument("--receipt", metavar="FILE", help="write a signed refusal receipt")
    s.add_argument("--overlay", metavar="PNG", help="write the findings overlay image")
    s.add_argument("--ledger", metavar="DIR", help="append the receipt to a ledger")
    s.add_argument("--advisory", action="store_true",
                   help="run the optional semantic advisory pass")
    s.add_argument("--on-behalf-of", metavar="ID", default=None)
    s.add_argument("--no-ocr", action="store_true",
                   help="skip the OCR render view (decision is unaffected)")
    s.set_defaults(func=cmd_scan)

    sa = sub.add_parser("sanitize", help="emit a cleaned copy, refuse if unsafe")
    sa.add_argument("path")
    sa.add_argument("-o", "--output", required=True, metavar="PATH")
    sa.set_defaults(func=cmd_sanitize)

    lg = sub.add_parser("ledger", help="ledger operations")
    lgsub = lg.add_subparsers(dest="ledger_command", required=True)
    lv = lgsub.add_parser("verify", help="verify receipt chain integrity")
    lv.add_argument("dir")
    lv.set_defaults(func=cmd_ledger_verify)

    kg = sub.add_parser("keygen", help="create the signing keypair")
    kg.set_defaults(func=cmd_keygen)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
