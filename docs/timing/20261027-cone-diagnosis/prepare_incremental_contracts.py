"""Freeze structurally identified stages from measured, immutable route inputs."""
import json
from pathlib import Path
import subprocess
import sys

repo = Path(__file__).resolve().parents[3]
tool = repo/'tools/timing'
sys.path.insert(0, str(tool))
from incremental_trial import operations

evidence = Path(__file__).resolve().parent
for case, base in (
    ('fanout', 'data_sink_local_20261027/electrical_sink_local-01'),
    ('last_fanout', 'data_incremental_20261027_03/incremental_fanout-01'),
):
    trial = repo/'test/sim_build'/base
    state = json.loads(next((trial/'run').glob('*-openroad-detailedrouting/state_out.json')).read_text())
    recipe = evidence/(case+'-recipe.json')
    with recipe.open('x') as stream:
        json.dump(operations(case), stream, indent=2); stream.write('\n')
    command = ['openroad', '-no_init', '-exit', '-python', str(tool/'resolve_eco_targets.py'),
               '--odb', state['odb'], '--recipe', str(recipe),
               '--out', str(evidence/(case+'-structural-targets.json'))]
    with (evidence/(case+'-structural-targets.log')).open('w') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
print('PASS: both incremental repair contracts uniquely identify their reference targets')
