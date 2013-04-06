Stalker Monitoring System - PoC
===============================

Components:
 
 - stalker_agent - Runs on the clients, registers the client with the master, executes local checks.
 - stalkerweb - Client registration end point and Web UI
 - stalker_manager - Just parses the master db and puts work on the queue for the runners.
 - stalker_runner - Reads work queue, hits clients stalker_agent to run checks, schedules checks next run
 - MongoDB (its what I had installed...could be anything else). Just stores check states and host config info.
 - Redis - Could do without now, but handy if we run multiple stalker_runners down the road


## stalker_agent.py

stalker_agent.py runs on all client boxes. On boot it looks in stalker-agent.conf for defined checks, but you can also just drop scripts in `script_dir` and it will automatically use them as well . Once its discovered what checks should be run it notifies stalkerweb and reports what checks it found installed and configured, and at what interval they should be run at. It then fires
up a wsgi app on port 5050 to listen for requests to run installed checks. You can trigger a check be run like so:

    fhines@ubuntu:~/stalker (master)[virt]$ http http://localhost:5050/check_load X-CHECK-KEY:canhazstatus
    HTTP/1.1 200 OK
    Content-Length: 173
    Content-Type: application/json
    Date: Mon, 25 Mar 2013 04:36:44 GMT
    
    {
        "check_load": {
            "err": "", 
            "out": "OK - load average: 0.01, 0.08, 0.12|load1=0.010;1.000;2.000;0; load5=0.080;5.000;10.000;0; load15=0.120;10.000;15.000;0;", 
            "status": 0
        }
    }
    
## stalkerweb

Stalkerweb simply listens for agents to register themselves and then inserts their info (hostname, src ip, checks to run,
roles, etc) into a central database. In addition it also exposes a simple web interface and api to query for active
checks or configured hosts. In addition to the UI running on http://stalkerweb:5000/ theres also a few api calls exposed that return a JSON response:

| URI	| Description | Methods |
|-------|---------------|-----------|
| /register/ |	stalker_agent registration end point |  POST |
| /hosts/ | All hosts | GET |
| /hosts/<hostname> |  Config for a specific host | GET |
| /checks/ | All checks | GET |
| /checks/<hostname> | Checks for a specific host | GET |
| /checks/state/<state> |  All checks for a given state [alerting, pending, in_maintenance] | GET |

## stalker_manager

stalker-manager is charge of scheduling checks with runners. At the moment it really just checks the db for checks that need to be run and drop's them on a Redis queue.

## stalker_runner

It pulls checks out of a Redis list. Then makes the http call for the check to the agent. It parses the result and updates the database accordingly (i.e. marking a check as failed, setting the next run time, etc). It also does some vary basic flap detection.

## TODO's

See issues. (Theres lots)