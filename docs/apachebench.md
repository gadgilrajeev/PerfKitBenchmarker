# Apachebench Test

## How the test works
The apachebench benchmark in the perfkitbenchmarker repository is a tool designed to measure the performance of web servers. It utilizes the Apache HTTP server benchmarking tool, ab, to simulate concurrent user traffic and stress test the web server. The benchmark generates a configurable number of HTTP requests and measures metrics such as throughput (requests per second), latency (response time), and requests per minute (RPM). By running apachebench against different web server endpoints, it allows for the evaluation of performance, scalability, and responsiveness under varying workloads. 

## Configuration options and defaults
To access the help for this test, run the following command  
```./pkb.py --helpmatch=apachebench```  

perfkitbenchmarker.linux_benchmarks.apachebench_benchmark:
```
  --apachebench_client_vms: The number of client VMs to use.
    (default: '1')
    (an integer)
  --apachebench_concurrency: Number of multiple requests to perform at a time.
    (default: '1')
    (an integer)
  --apachebench_http_method: <GET|POST|PUT|PATCH|DELETE>: Custom HTTP method for the requests.
    (default: 'GET')
  --[no]apachebench_keep_alive: Enable the HTTP KeepAlive feature.
    (default: 'true')
  --apachebench_max_concurrency: The maximum number of concurrent requests to use when searching for max throughput (when --apachebench_run_mode=MAX_THROUGHPUT).
    (default: '1000')
    (integer <= 1024)
  --apachebench_num_requests: Number of requests to perform for the benchmarking session.
    (default: '10000')
    (an integer)
  --apachebench_run_mode: <MAX_THROUGHPUT|STANDARD>: Specify which run mode to use.MAX_THROUGHPUT: Searches for concurrency level with max requests per second while
    keeping number of failed requests at 0. STANDARD: Runs Apache Bench with specified flags.
    (default: 'STANDARD')
  --apachebench_server_content_size: The size of the content the Apache server will serve (in bytes).
    (default: '2070000')
    (an integer)
  --apachebench_socket_timeout: Maximum number of seconds to wait before the socket times out.
    (default: '30')
    (an integer)
  --apachebench_timelimit: Maximum number of seconds to spend for benchmarking. After the timelimit is reached, additional requests will not be sent.
    (an integer)
```
### See example configuration here: 


## Metrics captured
CPU seconds (seconds):

Failed requests (#):

Raw Request Times (#):

Requests per second (#/sec):

Time per request concurrent (ms):

Time per request (ms):

Transfer rate (Kbytes/sec):

Total transferred (bytes):

HTML transferred (bytes):

End to end Runtime (seconds): 
The total runtime of the test from initiation to (teardown complete?)

