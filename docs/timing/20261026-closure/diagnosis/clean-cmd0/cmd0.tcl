# Diagnostic replay of a post-route netlist; not signoff constraints.
# Run in the matching LibreLane/OpenSTA + PDK environment. See
# docs/io_timing_implementation_plan.md for environment variables and limitations.
foreach name {PIO_TIMING_RUN PDK_ROOT PIO_TIMING_CORNER PIO_TIMING_MODE PIO_TIMING_OUT} {
    if {![info exists ::env($name)] || $::env($name) eq ""} {
        error "Required environment variable missing: $name"
    }
}
set run_dir [file normalize $::env(PIO_TIMING_RUN)]
set out_dir [file normalize $::env(PIO_TIMING_OUT)]
set mode $::env(PIO_TIMING_MODE)
if {$mode ni {baseline operational reset_active}} { error "Unsupported diagnostic mode" }
switch -- $::env(PIO_TIMING_CORNER) {
    nom_slow_1p08V_125C { set std_suffix slow_1p08V_125C; set io_suffix slow_1p08V_3p0V_125C }
    nom_typ_1p20V_25C { set std_suffix typ_1p20V_25C; set io_suffix typ_1p2V_3p3V_25C }
    nom_fast_1p32V_m40C { set std_suffix fast_1p32V_m40C; set io_suffix fast_1p32V_3p6V_m40C }
    default { error "Unsupported baseline corner" }
}
set pdk [file join $::env(PDK_ROOT) ihp-sg13cmos5l libs.ref]
set std_lib [file join $pdk sg13cmos5l_stdcell lib sg13cmos5l_stdcell_${std_suffix}.lib]
set io_lib [file join $pdk sg13cmos5l_io lib sg13cmos5l_io_${io_suffix}.lib]
proc unique_file {pattern} {
    set paths [glob -nocomplain $pattern]
    if {[llength $paths] != 1} { error "Expected exactly one artifact: $pattern; found $paths" }
    return [lindex $paths 0]
}
set netlist [unique_file [file join $run_dir *-openroad-fillinsertion tt_um_shanebri_top.nl.v]]
set spef [unique_file [file join $run_dir *-openroad-rcx nom tt_um_shanebri_top.nom.spef]]
set sdc [file join $run_dir final sdc tt_um_shanebri_top.sdc]
foreach path [list $std_lib $io_lib $netlist $spef $sdc] {
    if {![file isfile $path]} { error "Missing input: $path" }
}
file mkdir $out_dir
read_liberty $std_lib
read_liberty $io_lib
read_verilog $netlist
link_design tt_um_shanebri_top
set_cmd_units -time ns -capacitance pF -current mA -voltage V -resistance kOhm -distance um
read_sdc $sdc
read_spef $spef

set_case_analysis 1 [get_ports {ui_in[4]}]
set_case_analysis 0 [get_ports {ui_in[5]}]
set_case_analysis 0 [get_ports {ui_in[0]}]
set_case_analysis 0 [get_ports {ui_in[2]}]
set_case_analysis 0 [get_ports {ui_in[3]}]
set sta_report_default_digits 6

# This mode excludes reset transitions solely to expose functional paths.
# It is not a reset exception or a replacement for startup/release qualification.
# Keep ena dynamic: the RTL gives it runtime freeze/resume semantics.
if {$mode eq "operational"} { set_case_analysis 1 [get_ports rst_n] }
if {$mode eq "reset_active"} { set_case_analysis 0 [get_ports rst_n] }
puts "Diagnostic replay: $::env(PIO_TIMING_CORNER), $mode"
report_units
report_worst_slack -max > [file join $out_dir worst_setup.rpt]
report_worst_slack -min > [file join $out_dir worst_hold.rpt]
report_checks -path_delay max -sort_by_slack -group_path_count 30 \
    -fields {slew cap input net fanout} -format full_clock_expanded \
    > [file join $out_dir global_setup.rpt]
report_checks -path_delay min -sort_by_slack -group_path_count 30 \
    -fields {slew cap input net fanout} -format full_clock_expanded \
    > [file join $out_dir global_hold.rpt]

set launch [all_registers -clock_pins]
set capture [all_registers -data_pins]
if {[llength $launch] == 0 || [llength $capture] == 0} { error "No registers found" }
foreach delay {max min} {
    foreach edge {rise fall} {
        report_checks -${edge}_from [get_ports rst_n] -path_delay $delay \
            -sort_by_slack -group_path_count 30 -endpoint_path_count 2 \
            -fields {slew cap input net fanout} -format full_clock_expanded \
            > [file join $out_dir reset_${edge}_${delay}.rpt]
    }
    report_checks -from $launch -to $capture -path_delay $delay \
        -sort_by_slack -group_path_count 30 -endpoint_path_count 2 \
        -fields {slew cap input net fanout} -format full_clock_expanded \
        > [file join $out_dir registers_${delay}.rpt]
    # Per-port queries prevent reset from hiding other startpoints/endpoints.
    foreach port [all_inputs] {
        set name [get_property $port full_name]
        if {$name eq "clk"} { continue }
        set safe [string map {[ _ ] _ / _} $name]
        report_checks -from $port -path_delay $delay -sort_by_slack \
            -group_path_count 10 -endpoint_path_count 2 \
            -fields {slew cap input net fanout} -format full_clock_expanded \
            > [file join $out_dir input_${safe}_${delay}.rpt]
    }
    foreach port [all_outputs] {
        set name [get_property $port full_name]
        set safe [string map {[ _ ] _ / _} $name]
        report_checks -to $port -path_delay $delay -sort_by_slack \
            -group_path_count 10 -endpoint_path_count 2 \
            -fields {slew cap input net fanout} -format full_clock_expanded \
            > [file join $out_dir output_${safe}_${delay}.rpt]
    }
}
# The historical numerical pin is valid only for the frozen reference netlist.
# Candidate revisions use reset-to-all reports above, or an explicitly mapped pin.
set target_name "_32168_/D"
if {[info exists ::env(PIO_TIMING_TARGET)]} { set target_name $::env(PIO_TIMING_TARGET) }
if {$target_name eq "none"} { set target_name "" }
if {$mode eq "baseline" && $target_name ne ""} {
    set target [get_pins -quiet $target_name]
    if {[llength $target] != 1} { error "Mapped target pin missing: $target_name" }
    foreach edge {rise fall} {
        report_checks -${edge}_from [get_ports rst_n] -to $target \
            -path_delay max -group_path_count 5 -endpoint_path_count 5 \
            -fields {slew cap input net fanout} -format full_clock_expanded \
            > [file join $out_dir reset_${edge}_to_isr3.rpt]
    }
}
report_check_types -max_slew -max_capacitance -max_fanout -violators \
    > [file join $out_dir electrical.rpt]
report_parasitic_annotation -report_unannotated > [file join $out_dir annotation.rpt]
check_setup -verbose -unconstrained_endpoints -multiple_clock -no_clock \
    -no_input_delay -loops -generated_clocks > [file join $out_dir coverage.rpt]
write_sdc [file join $out_dir effective.sdc]
