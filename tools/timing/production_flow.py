"""Audited clean-build flow for the measured 50 MHz closure recipe.

Import from a LibreLane plugin to register PIOClosure. The ordinary Classic
frontend and complete signoff tail remain intact. All ECO targets are resolved
from a structural contract for this build and all transformations are audited.
"""
import json
from pathlib import Path
import subprocess
import sys

from librelane.common import Path as ViewPath
from librelane.config import Variable
from librelane.flows import Flow
from librelane.flows.classic import Classic
from librelane.state import DesignFormat
from librelane.steps import Step, StepError
from librelane.steps.openroad import DetailedPlacement, DetailedRouting, GlobalPlacement, GlobalRouting
from typing import List

from check_signoff import REQUIRED_CORNERS
from closure_trial import validate_config
from data_eco_trial import script
from incremental_trial import incremental_script
from finalize_routes import unfixed_nets_def

TOOL = Path(__file__).resolve().parent


def run_tool(step, name, arguments):
    command = ['openroad', '-no_init', '-exit', '-python', str(TOOL/name), *map(str, arguments)]
    with (Path(step.step_dir)/(Path(name).stem+'.log')).open('w') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)


class PlacementViews(GlobalPlacement):
    def __init__(self, config, *args, **kwargs):
        # The measured placement used the original 0.30 capacity adjustment.
        # 0.25 was introduced at later routing; GPL's internal routing also
        # consumes this setting, so applying 0.25 here changes the placement.
        super().__init__(config.copy(PNR_CORNERS=list(REQUIRED_CORNERS),
                                     GRT_ADJUSTMENT=.30), *args, **kwargs)


class ClockRepair(DetailedPlacement):
    id = 'OpenROAD.RepairClockFanout'
    name = 'Audited clock branch repair'

    def get_script_path(self):
        return str(TOOL/'repair_clock_fanout.tcl')

    def run(self, state_in, **kwargs):
        views, metrics = super().run(state_in, **kwargs)
        run_tool(self, 'audit_clock_tree.py', ['--before', state_in[DesignFormat.ODB],
                 '--odb', views[DesignFormat.ODB], '--out', Path(self.step_dir)/'clock_audit.json'])
        return views, metrics


class PrepareSignalRoutes(Step):
    id = 'PIO.PrepareSignalRoutes'
    inputs = [DesignFormat.ODB, DesignFormat.DEF]
    outputs = [DesignFormat.ODB, DesignFormat.DEF]

    def run(self, state_in, **kwargs):
        out = Path(self.step_dir)/'prepared'
        run_tool(self, 'prepare_data_eco.py', ['--state', Path(self.step_dir)/'state_in.json', '--out', out])
        return {DesignFormat.ODB: ViewPath(str(out/'unrouted.odb')),
                DesignFormat.DEF: ViewPath(str(out/'unrouted.def'))}, {}


class DataRepair(DetailedPlacement):
    id = 'OpenROAD.DataECO'
    name = 'Structurally identified and audited data repair'
    config_vars = DetailedPlacement.config_vars + [
        Variable('PIO_ECO_CONTRACT', ViewPath, 'Validated connectivity fingerprints and repair recipe')]

    def contract(self):
        return self.config['PIO_ECO_CONTRACT']

    def render_script(self, operations):
        return script(operations)

    def get_script_path(self):
        return str(Path(self.step_dir)/'eco.tcl')

    def run(self, state_in, **kwargs):
        recipe = Path(self.step_dir)/'resolved_recipe.json'
        run_tool(self, 'resolve_eco_targets.py', ['--odb', state_in[DesignFormat.ODB],
                 '--contract', self.contract(), '--out', recipe])
        operations = json.loads(recipe.read_text())
        Path(self.get_script_path()).write_text(self.render_script(operations))
        views, metrics = super().run(state_in, **kwargs)
        model = Path(self.config['PDK_ROOT'])/'ihp-sg13cmos5l/libs.ref/sg13cmos5l_stdcell/verilog/sg13cmos5l_stdcell.v'
        run_tool(self, 'audit_data_eco.py', ['--before', state_in[DesignFormat.ODB],
                 '--odb', views[DesignFormat.ODB], '--recipe', recipe, '--pdk-model', model,
                 '--out', Path(self.step_dir)/'eco_audit.json'])
        return views, metrics


class IncrementalRepair(DataRepair):
    id = 'OpenROAD.IncrementalFanoutRepair'
    name = 'Audited post-antenna fanout repair with incremental global routing'
    config_vars = GlobalRouting.config_vars + [
        Variable('PIO_INCREMENTAL_ECO_CONTRACTS', List[ViewPath],
                 'Ordered structural contracts for post-route load repairs')]
    contract_index = 0

    def contract(self):
        return self.config['PIO_INCREMENTAL_ECO_CONTRACTS'][self.contract_index]

    def render_script(self, operations):
        return incremental_script(operations)


class LastFanoutRepair(IncrementalRepair):
    id = 'OpenROAD.LastFanoutRepair'
    contract_index = 1

    def run(self, state_in, **kwargs):
        views, metrics = super().run(state_in, **kwargs)
        preserved = Path(self.step_dir)/'preserved'
        run_tool(self, 'preserve_routes.py', ['--before', state_in[DesignFormat.ODB],
            '--before-def', state_in[DesignFormat.DEF], '--after', views[DesignFormat.ODB],
            '--after-def', views[DesignFormat.DEF], '--out', preserved])
        views[DesignFormat.ODB] = ViewPath(str(preserved/'preserved.odb'))
        views[DesignFormat.DEF] = ViewPath(str(preserved/'preserved.def'))
        return views, metrics


class FinalizeRoutes(DetailedRouting):
    id = 'OpenROAD.FinalizeRoutes'
    name = 'Native route finalization with serialized-geometry audit'

    def get_script_path(self):
        return str(Path(self.step_dir)/'finalize.tcl')

    def run(self, state_in, **kwargs):
        unfixed = Path(self.step_dir)/'unfixed.def'
        unfixed.write_text(unfixed_nets_def(Path(state_in[DesignFormat.DEF]).read_text()))
        native = Path(DetailedRouting.get_script_path(self)).read_text()
        if native.count('read_current_odb') != 1:
            raise StepError('Native routing entrypoint changed')
        Path(self.get_script_path()).write_text(native.replace('read_current_odb',
            'read_current_odb\nread_def -floorplan_initialize {'+str(unfixed)+'}',1))
        views, metrics = super().run(state_in, **kwargs)
        run_tool(self, 'finalize_routes.py', ['--before',state_in[DesignFormat.ODB],
            '--before-def',state_in[DesignFormat.DEF], '--after',views[DesignFormat.ODB],
            '--after-def',views[DesignFormat.DEF], '--out',Path(self.step_dir)/'finalization_audit.json'])
        return views, metrics


class RouteAcceptance(Step):
    id = 'PIO.RouteAcceptance'
    inputs = [DesignFormat.ODB, DesignFormat.NETLIST, DesignFormat.SDC, DesignFormat.SPEF]
    outputs = []

    def run(self, state_in, **kwargs):
        command = [sys.executable, str(TOOL/'qualify_final_route.py'), '--run', str(Path(self.step_dir).parent),
                   '--pdk-root', str(self.config['PDK_ROOT']), '--out', str(Path(self.step_dir)/'qualification')]
        with (Path(self.step_dir)/'qualification.log').open('w') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        return {}, {}


steps = []
first_grt = next(i for i, s in enumerate(Classic.Steps) if s.id == 'OpenROAD.GlobalRouting')
first_drt = next(i for i, s in enumerate(Classic.Steps) if s.id == 'OpenROAD.DetailedRouting')
for original in Classic.Steps[:first_drt+1]:
    steps.append(PlacementViews if original.id == 'OpenROAD.GlobalPlacement' else original)
    if original.id == 'OpenROAD.CTS':
        steps.append(ClockRepair)
steps.extend([PrepareSignalRoutes, DataRepair])
steps.extend(Classic.Steps[first_grt:first_drt+1])
steps.extend([IncrementalRepair, Classic.Steps[first_drt], LastFanoutRepair])
for original in Classic.Steps[first_drt:]:
    steps.append(original)
    if original.id == 'OpenROAD.DetailedRouting':
        steps.append(FinalizeRoutes)
    if original.id == 'OpenROAD.STAPostPNR':
        steps.append(RouteAcceptance)


@Flow.factory.register()
class PIOClosure(Classic):
    Steps = steps
    # SequentialFlow adds -1/-2 to repeated native IDs. Preserve the native
    # enable switches on every routing pass, including normally disabled repair.
    gating_config_vars = {key if key.endswith('*') else key+'*': value
                          for key, value in Classic.gating_config_vars.items()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        validate_config(self.config)
        if (self.config['GRT_ADJUSTMENT'] != .25 or self.config['CTS_SINK_CLUSTERING_SIZE'] is not None
                or not self.config['PL_TIMING_DRIVEN'] or self.config['OPENROAD_THREADS'] != 8):
            raise StepError('Measured implementation settings changed')
        if len(self.config['PIO_INCREMENTAL_ECO_CONTRACTS']) != 2:
            raise StepError('Expected the two measured post-route repair stages')
