# Bidirectional Network Test

## How the test works
The bidirectional_network benchmark in the perfkitbenchmarker repository is a tool designed to measure the network performance between two virtual machines (VMs) by simulating bidirectional network traffic. It evaluates the network bandwidth and latency by transmitting data between the source and destination VMs in both directions simultaneously. The benchmark allows for customization of parameters such as the packet size, number of parallel streams, and duration of the test.

## Configuration options and defaults
To access the help for this test, run the following command  
```./pkb.py --helpmatch=bidirectional_network```  

perfkitbenchmarker.linux_benchmarks.bidirectional_network_benchmark:
```
  --bidirectional_network_test_length: bidirectional_network test length, in seconds
    (default: '60')
    (a positive integer)
  --bidirectional_network_tests: The network tests to run.
    (default: 'TCP_STREAM,TCP_MAERTS,TCP_MAERTS')
    (a comma separated list)
  --bidirectional_stream_num_streams: Number of netperf processes to run.
    (default: '8')
    (a positive integer)
```
### See example configuration here: 


## Metrics captured
TCP_MAERTS_Throughput (Mbytes/sec):

TCP_STREAM_Throughput (Mbytes/sec):
	
inbound_network_total (Mbytes/sec):

outbound_network_total (Mbytes/sec):

TCP_STREAM_start_delta (sec):

TCP_MAERTS_start_delta (sec):

all_streams_start_delta (sec):

End to end Runtime (seconds): 
The total runtime of the test from initiation to (teardown complete?)

