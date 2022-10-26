#!/usr/bin/tclsh
puts "SETTING CONFIGURATION"

proc wait_to_complete { seconds } {
  set x 0
  set timerstop 0
  while {!$timerstop} {
   incr x
   after 1000
    if { ![ expr {$x % 60} ] } {
    set y [ expr $x / 60 ]
    puts "Timer: $y minutes elapsed"
    }
   update
   if {  [ vucomplete ] || $x eq $seconds } { set timerstop 1 }
  }
  return
}
puts "SETTING CONFIGURATION"

vudestroy
dbset db mysql
dbset bm TPC-C
diset connection mysql_host {{DATABASE_IP}}
diset connection mysql_port {{DATABASE_PORT}}
diset tpcc mysql_pass {{DATABASE_PASSWORD}}
diset tpcc mysql_user {{DATABASE_USER}}
diset tpcc mysql_count_ware {{NUM_WAREHOUSE_TPC_C}}
diset tpcc mysql_allwarehouse {{ALL_WAREHOUSE_TPC_C}}
diset tpcc mysql_num_vu {{VIRTUAL_USERS_TPC_C}}
diset tpcc mysql_timeprofile {{TIME_PROFILE_TPC_C}}
if {{{LOG_TRANSACTIONS}}} {
  tcset logtotemp 1
  tcset timestamps 1
  tcset refreshrate 1
}
diset tpcc mysql_driver timed
diset tpcc mysql_rampup {{RAMPUP_TPC_C}}
diset tpcc mysql_duration {{DURATION_TPC_C}}
vuset logtotemp 1

puts "Loading script"
loadscript

puts "TEST SEQUENCE STARTED"
vudestroy
puts "{{VIRTUAL_USERS_TPC_C}} VU TEST"
vuset vu {{VIRTUAL_USERS_TPC_C}}
vucreate
if {{{LOG_TRANSACTIONS}}} {
  tcstart
  tcstatus
}
vurun
wait_to_complete {{WAIT_TO_COMPLETE}}
vudestroy

if {{{LOG_TRANSACTIONS}}} {
  tcstop
}

puts "TEST SEQUENCE COMPLETE"
