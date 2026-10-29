source {/mnt/c/Users/shane/Projects/JaneStreet-protocol-emulator-ASIC-competition/tools/timing/report_io_paths.tcl}
set targets [get_pins {_31995_/D}]
foreach delay {max min} {
    report_checks -to $targets -path_delay $delay -sort_by_slack -group_path_count 1000 -endpoint_path_count 16 -fields {slew cap input net fanout} -format full_clock_expanded > [file join $out_dir cone_${delay}.rpt]
    foreach port [all_inputs] {
        set name [get_property $port full_name]
        if {$name eq "clk"} {continue}
        set safe [string map {[ _ ] _ / _} $name]
        report_checks -from $port -to $targets -path_delay $delay -sort_by_slack -group_path_count 1000 -endpoint_path_count 4 -fields {slew cap input net fanout} -format full_clock_expanded > [file join $out_dir cone_input_${safe}_${delay}.rpt]
    }
    report_checks -from [all_registers -clock_pins] -to $targets -path_delay $delay -sort_by_slack -group_path_count 1000 -endpoint_path_count 8 -fields {slew cap input net fanout} -format full_clock_expanded > [file join $out_dir cone_registers_${delay}.rpt]
    report_checks -path_delay $delay -sort_by_slack -group_path_count 100 -endpoint_path_count 4 -fields {slew cap input net fanout} -format full_clock_expanded > [file join $out_dir competing_${delay}.rpt]
}
foreach driver {_17710_/Y _17942_/Y _28912_/Y _28923_/Y _17226_/Y _17250_/Y _17236_/X _17262_/X} {
    set safe [string map {/ _} $driver]
    report_checks -through [get_pins $driver] -path_delay max -sort_by_slack -group_path_count 200 -endpoint_path_count 4 -fields {slew cap input net fanout} -format full_clock_expanded > [file join $out_dir through_${safe}.rpt]
    report_net -connections [get_property [get_nets -of_objects [get_pins $driver]] full_name] > [file join $out_dir net_${safe}.rpt]
}
