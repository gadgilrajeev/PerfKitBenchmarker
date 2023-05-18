# Coremark Test

## How the test works
The coremark benchmark in the perfkitbenchmarker repository is a tool used to evaluate the performance and capabilities of processors and embedded systems. It measures the performance of the CPU by executing a series of tasks that simulate typical embedded system workloads. The benchmark focuses on evaluating the processor's ability to perform integer operations, loop processing, and basic control flow. It provides a CoreMark score, which represents the number of iterations executed per second.

## Configuration options and defaults
To access the help for this test, run the following command  
```./pkb.py --helpmatch=coremark```  

perfkitbenchmarker.linux_benchmarks.coremark_benchmark:
```
  --coremark_parallelism_method: <PTHREAD|FORK|SOCKET>: Method to use for parallelism in the Coremark benchmark.
    (default: 'PTHREAD')
```
### See example configuration here: 

## Metrics captured
Coremark Score (#):
The Coremark score is a measure of the performance of a computing system based on the Coremark benchmark. It represents the number of iterations completed within a specified time frame, indicating the system's ability to execute the benchmark workload. A higher Coremark score generally indicates better performance.

End to end Runtime (seconds): 
The total runtime of the test from initiation to (teardown complete?)
