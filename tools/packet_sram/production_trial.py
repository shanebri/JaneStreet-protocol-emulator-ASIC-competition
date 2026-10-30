"""Freeze a host-only SRAM candidate and run the normal pinned production flow.

Active production files are never modified. Failed candidate sources and logs
are retained in the trial directory; no candidate is promoted automatically.
The available -55 C fast macro model is diagnostic, not exact -40 C signoff.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "test/sim_build/packet_sram_production_20261030_03"
PDK = Path("/home/shane/eda/pdk-2bbec755")
TOOLING = REPO / "test/sim_build/production_tooling"


def freeze():
    ROOT.mkdir(parents=True, exist_ok=False)
    (ROOT / "run").mkdir()
    for folder in ("src", "tools/timing", "test"):
        shutil.copytree(REPO / folder, ROOT / folder,
                        ignore=shutil.ignore_patterns("sim_build", "__pycache__", "*.fst", "*.vcd",
                                                    "gate_level_netlist.v", "results.xml"))
    for file in ("info.yaml", "librelane_plugin_pio.py"):
        shutil.copy2(REPO / file, ROOT / file)
    (ROOT / "tt").symlink_to(TOOLING / "tt", target_is_directory=True)
    shutil.copy2(REPO / "tools/packet_sram/trial_portal.sv", ROOT / "src/packet/packet_sram_portal.sv")
    shutil.copy2(REPO / "tools/packet_sram/macro_blackbox.v", ROOT / "src/packet/macro_blackbox.v")
    info = ROOT / "info.yaml"
    info.write_text(info.read_text().replace('    - "project.sv"',
        '    - "project.sv"\n    - "packet/packet_sram.sv"\n    - "packet/packet_sram_portal.sv"'))
    path = ROOT / "src/pio_subsystem.sv"
    text = path.read_text().replace("    genvar e;", """
    wire [31:0] packet_read [0:1];
    packet_sram_portal packet (.clk(clk), .rst_n(rst_n), .enable(enable),
        .commit(|word_write), .selector(selected_engine ? data_address[1] : data_address[0]),
        .data(selected_engine ? write_word[1] : write_word[0]),
        .read_selector0(data_address[0]), .read_selector1(data_address[1]),
        .read0(packet_read[0]), .read1(packet_read[1]));
    genvar e;""")
    text = text.replace("selector <= 8'h1e;", "selector <= 8'h1e || (selector >= 8'h20 && selector <= 8'h24);")
    text = text.replace("                default: ;", "                8'h20,8'h21,8'h22,8'h23,8'h24: bank_selected_data = packet_read[e];\n                default: ;", 1)
    path.write_text(text)
    config_path = ROOT / "src/config.json"
    config = json.loads(config_path.read_text())
    macro = "RM_IHPSG13_1P_64x16_c2"
    base = PDK / "ihp-sg13cmos5l/libs.ref/sg13cmos5l_sram"
    config["MACROS"] = {macro: {
        "lef": [str(base / "lef" / (macro + ".lef"))],
        "gds": [str(base / "gds" / (macro + ".gds"))],
        "spice": [str(base / "cdl" / (macro + ".cdl"))],
        "vh": [str(ROOT / "src/packet/macro_blackbox.v")],
        "lib": {corner: [str(base / "lib" / (macro + "_" + suffix + ".lib"))] for corner, suffix in (
            ("nom_slow_1p08V_125C", "slow_1p08V_125C"),
            ("nom_typ_1p20V_25C", "typ_1p20V_25C"),
            ("nom_fast_1p32V_m40C", "fast_1p32V_m55C"))},
        "instances": {"pio.packet.storage.memory": {"location": [740, 310], "orientation": "N"}}
    }}
    config["PDN_MACRO_CONNECTIONS"] = [r"pio\.packet\.storage\.memory VPWR VGND VDD! VSS!"]
    config["FP_MACRO_HORIZONTAL_HALO"] = 10
    config["FP_MACRO_VERTICAL_HALO"] = 10
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    # Count the explicit macro clock as a clock sink; preserve all clock audits.
    audit = ROOT / "tools/timing/audit_clock_tree.py"
    audit.write_text(audit.read_text().replace("if name == 'CLK':", "if name == 'CLK' or (name == 'A_CLK' and inst.getMaster().getName() == 'RM_IHPSG13_1P_64x16_c2'):"))
    files = [p for folder in ("src", "tools/timing", "test") for p in (ROOT / folder).rglob("*") if p.is_file()]
    files += [info, ROOT / "librelane_plugin_pio.py"]
    (ROOT / "frozen_inputs.json").write_text(json.dumps({str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}, indent=2) + "\n")
    (ROOT / "scope.json").write_text(json.dumps(dict(parent="bb7c5ef3c54a7ae2733bbfae82aa940016375007",
        production_flow="PIOClosure", active_design_modified=False,
        fast_model_substitution="SRAM -55 C model explicitly used for diagnostic implementation only; exact -40 C qualification remains unavailable",
        disposition="No promotion without complete normal signoff and no timing/electrical regression"), indent=2) + "\n")


def worker():
    state = dict(status="running", commands=[], physical_signoff=False)
    def save(): (ROOT / "job.json").write_text(json.dumps(state, indent=2) + "\n")
    def run(command, name, env=None):
        state["commands"].append(command); save()
        with (ROOT / (name + ".log")).open("w") as log:
            subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    try:
        env = dict(os.environ, PYTHONPATH="", PATH=str(TOOLING / "venv/bin") + ":" + os.environ["PATH"],
                   XDG_CACHE_HOME=str(ROOT / ".cache"))
        run([str(TOOLING / "venv/bin/python"), str(ROOT / "tt/tt_tool.py"), "--create-user-config", "--ihp"], "configure", env)
        run([sys.executable, "-m", "librelane", "--pdk", "ihp-sg13cmos5l", "--manual-pdk",
             "--pdk-root", str(PDK), "--run-tag", "sram", "--force-run-dir", str(ROOT / "run"),
             "src/config_merged.json"], "production")
        # A complete run still cannot qualify the missing exact SRAM corner.
        state.update(status="rejected", reason="Exact fast -40 C SRAM characterization unavailable")
    except Exception as exc:
        state.update(status="failed", error=str(exc))
    finally:
        state["candidate_promoted"] = False
        save()


if __name__ == "__main__":
    if "--worker" in sys.argv:
        worker()
    else:
        freeze()
        command = ["/nix/var/nix/profiles/default/bin/nix", "develop", "--offline", "--command",
                   "python3", "-B", str(Path(__file__).resolve()), "--worker"]
        with (ROOT / "launcher.log").open("w") as log:
            proc = subprocess.Popen(command, cwd="/home/shane/eda/librelane-3.1.0.dev3",
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        (ROOT / "process.json").write_text(json.dumps(dict(pid=proc.pid, command=command), indent=2) + "\n")
        print("Started frozen production SRAM trial", proc.pid)
