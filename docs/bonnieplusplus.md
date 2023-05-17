# Bonnie Plus Plus Test

## How the test works
The bonnieplusplus benchmark in the perfkitbenchmarker repository is a tool used to assess the performance and capabilities of file systems and storage devices. It performs a series of tests to measure metrics such as sequential and random file I/O performance, file creation and deletion speed, as well as metadata operations. The benchmark generates synthetic workloads that simulate real-world file system usage scenarios. By executing the bonnieplusplus benchmark, it is possible to evaluate the read and write throughput, latency, and scalability of file systems and storage devices.

## Configuration options and defaults
To access the help for this test, run the following command  
```./pkb.py --helpmatch=bonnieplusplus```  

perfkitbenchmarker.linux_benchmarks.bonnieplusplus:
```
  N/A
```
### See example configuration here: 


## Metrics captured
put_block_cpu (%s):

rewrite_cpu (%s):

get_block_cpu (%s):

seeks_cpu (%s):

seq_create_cpu (%s):

seq_del_cpu (%s):

ran_create_cpu (%s):

ran_del_cpu (%s):

put_block_latency (ms):

rewrite_latency (ms):

get_block_latency (ms):

seeks_latency (ms):

seq_create_latency (us):

seq_stat_latency (us):

seq_del_latency (us):

ran_create_latency (us):

ran_stat_latency (us):

ran_del_latency (us):

put_block (K/sec):

rewrite (K/sec):

get_block (K/sec):

seeks (K/sec):

seq_create (K/sec):

seq_del (K/sec):

ran_create (K/sec):

ran_del (K/sec):

End to end Runtime (seconds): 
The total runtime of the test from initiation to (teardown complete?)
