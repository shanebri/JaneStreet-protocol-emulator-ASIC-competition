"""Assembler for this project's PIO V0 ISA (not the Raspberry Pi toolchain).

Usage: python tools/pioasm.py examples/uart_v0.asm
Labels and [delay] are supported; optional side-set is written `side 0/1`.
"""
import argparse
import re
from pathlib import Path

SOURCES = dict(pins=0, x=1, y=2, null=3, status=5, isr=6, osr=7)
DESTS = dict(pins=0, x=1, y=2, null=3, pindirs=4, pc=5, isr=6, exec=7)
CONDS = {"always": 0, "!x": 1, "x--": 2, "!y": 3, "y--": 4,
         "x!=y": 5, "pin": 6, "!osre": 7}


def encode(op, arg=0, delay=0, side=None, sideset=False):
    if not 0 <= op < 8 or not 0 <= arg < 256:
        raise ValueError("opcode/argument out of range")
    if side is not None and not sideset:
        raise ValueError("side requires .sideset")
    if not 0 <= delay <= (7 if sideset else 31):
        raise ValueError("delay out of range")
    if side not in (None, 0, 1):
        raise ValueError("side must be 0 or 1")
    field = delay | ((0x10 | (side << 3)) if side is not None else 0)
    return (op << 13) | (field << 8) | arg


def assemble(text):
    labels, lines = {}, []
    sideset = False
    for line in text.splitlines():
        line = line.split(";", 1)[0].strip().lower()
        if not line:
            continue
        if line == ".sideset":
            sideset = True
            continue
        label_match = re.match(r"^([a-z_][a-z0-9_]*):\s*", line)
        if label_match:
            label = label_match[1]
            line = line[label_match.end():]
            if label in labels:
                raise ValueError(f"duplicate label: {label}")
            labels[label] = len(lines)
            line = line.strip()
        if line:
            lines.append(line)
    if len(lines) > 32:
        raise ValueError("program exceeds 32 words")
    words = []
    for line in lines:
        original = line
        try:
            delay = 0
            match = re.search(r"\[(\d+)\]$", line)
            if match:
                delay = int(match[1])
                line = line[:match.start()].strip()
            side = None
            match = re.search(r"\bside\s+([01])$", line)
            if match:
                side = int(match[1])
                line = line[:match.start()].strip()
            tokens = line.replace(",", " ").split()
            mnemonic, operands = tokens[0], tokens[1:]
            if mnemonic == "nop":
                assert not operands
                op, arg = 5, 0x42  # MOV Y,Y
            elif mnemonic == "halt":
                assert not operands
                op, arg = 6, 0x80
            elif mnemonic == "jmp":
                assert len(operands) in (1, 2)
                condition = CONDS[operands[0]] if len(operands) == 2 else 0
                target = labels[operands[-1]] if operands[-1] in labels else int(operands[-1], 0)
                assert 0 <= target < 32
                op, arg = 0, (condition << 5) | target
            elif mnemonic == "wait":
                assert len(operands) == 3
                polarity, source, index = int(operands[0], 0), operands[1], int(operands[2], 0)
                assert polarity in (0, 1)
                assert 0 <= index < (8 if source == "irq" else 6)
                op, arg = 1, (polarity << 7) | ({"gpio": 0, "pin": 1, "irq": 2}[source] << 5) | index
            elif mnemonic in ("in", "out"):
                assert len(operands) == 2
                target, count = operands[0], int(operands[1], 0)
                assert 1 <= count <= 32
                table = SOURCES if mnemonic == "in" else DESTS
                assert mnemonic != "in" or target != "status"
                op, arg = (2 if mnemonic == "in" else 3), (table[target] << 5) | (count & 31)
            elif mnemonic in ("push", "pull"):
                conditional = "ifempty" if mnemonic == "pull" else "iffull"
                assert all(v in (conditional, "block", "noblock") for v in operands)
                assert len(set(operands)) == len(operands)
                assert not ("block" in operands and "noblock" in operands)
                op, arg = 4, ((mnemonic == "pull") << 7) | ((conditional in operands) << 6) | (("noblock" not in operands) << 5)
            elif mnemonic == "mov":
                assert len(operands) == 2
                target, source = operands
                operation = 1 if source.startswith("~") else 2 if source.startswith("::") else 0
                source = source.lstrip("~:")
                dest = dict(pins=0, x=1, y=2, exec=4, pc=5, isr=6, osr=7)[target]
                op, arg = 5, (dest << 5) | (operation << 3) | SOURCES[source]
            elif mnemonic == "irq":
                assert len(operands) == 2
                index = int(operands[1], 0)
                assert 0 <= index < 8
                op, arg = 6, {"set": 0, "wait": 32, "clear": 64}[operands[0]] | index
            elif mnemonic == "set":
                assert len(operands) == 2
                value = int(operands[1], 0)
                assert 0 <= value < 32
                op, arg = 7, ({"pins": 0, "x": 1, "y": 2, "pindirs": 4}[operands[0]] << 5) | value
            else:
                raise ValueError("unknown mnemonic")
            words.append(encode(op, arg, delay, side, sideset))
        except (AssertionError, KeyError, ValueError) as exc:
            raise ValueError(f"invalid instruction: {original}") from exc
    return words


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.source.with_suffix(".hex")
    output.write_text("".join(f"{word:04X}\n" for word in assemble(args.source.read_text())))
    print(output)


if __name__ == "__main__":
    main()
