"""Long service-rate checks so initial FIFO reserve cannot conceal a deficit."""
import json
import os
from pathlib import Path
import cocotb
from test_streaming import run_case


@cocotb.test()
async def long_packed_service_rate(dut):
    rows=[]
    for length,batch in ((1024,False),(1024,True),(4096,True)):
        row=await run_case(dut,length,packed=True,batch=batch,gap=512)
        rows.append(row)
        Path(os.environ['STREAM_RESULTS']).write_text(json.dumps(dict(clock_ns=20,rows=rows),indent=2)+'\n')
        print('LONG',row['depth'],length,batch,row['elapsed_clocks'],row['stalls'],flush=True)
    assert all(s['tx_stall']==0 and s['rx_stall']==0 for s in rows[-1]['stalls'])
