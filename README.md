Stalker Monitoring System - PoC
===============================

Components:
 
 - stalker_agent - Runs on the clients, registers the client with the master, executes local checks.
 - stalkerweb - Client registration end point and API server
 - stalkerd - backend server that actually manages checks/notification/alerting etc
 - RethinkDB - central db for storing host info, checks, notifications, and state log
 - Redis - Could do without now, but handy if we run multiple stalker_runners down the road

## stalker_agent.py

stalker_agent.py runs on all client boxes. On boot it looks in stalker-agent.conf for defined checks, but you can also just drop scripts in `script_dir` and it will automatically use them as well . Once its discovered what checks should be run it notifies stalkerweb and reports what checks it found installed and configured, and at what interval they should be run at. It then fires
up a wsgi app on port 5050 to listen for requests to run installed checks. You can trigger a check to be run like so:

    fhines@ubuntu:~/stalker (master)[virt]$ http https://localhost:5050/check_load X-CHECK-KEY:canhazstatus
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
| /global/clusters | Config info for all known stalker clusters | GET |
| /stats | Statistics for local instance| GET |
| /stats/[clusterid] | Statistics for remote stalker clusters | GET |
| /findhost | Just used for the type ahead in the UI | GET |
| /register/ | stalker_agent registration end point |  POST |
| /hosts/ | All hosts | GET |
| /hosts/[hostname] |  Config for a specific host | GET, DELETE |
| /checks/ | All checks | GET |
| /checks/host/[hostname] | checks matching to a specific host or ip | GET |
| /checks/id/[checkid] | A specific check | GET, DELETE |
| /checks/id/[checkid]/next | Get or Set next run time | GET, POST |
| /checks/id/[checkid]/suspended | Get or Set suspend state | GET, POST |
| /checks/state/[state] |  All checks for a given state [alerting, pending, in_maintenance] | GET |
| /global/[clusterid]/checks/state/[state] | All checks for a given state in a remote stalker claster | GET |
| /user/ | List all users | GET |
| /user/[username] | List/Modify/Delete a user | GET, POST, DELETE |
| /routes/list | Get a list of all available flask routes | GET |

## stalkerd

Stalkerd is the daemon that runs the whole thing. Internally it actually consists of 2 components. 

The manager portion is in charge of scheduling checks. It's constantly scanning the db for checks that need to be run and drop's them on a Redis queue. It also does things like make sure that the db is in consistent state and shuffles checks at start to make sure things are appropriately staggered upon restart.

The runner portion pulls checks out of the Redis list. Then it makes the http call for the check to the agent. It parses the result and updates the database accordingly (i.e. marking a check as failed, setting the next run time, etc). It also handles basic flap detection, host and global level flood detection , and handles notifications using any enabled notification plugins.

## Notification Plugins

 - Pagerduty Incident API (Support's triggering and resolving)
 - Mailgun API
 - Twilio
 - ~~Email via smtplib~~
 - ~~Shell Command Execution~~
 - ~~Generic HTTP POST~~

## TODO's

See issues and go/TODO (Theres lots). The current version of stalkerd is a line by line port of the python version (and switching to Rethink). Its less than ideal and not really very idiomatic go. The port was the first step. Now we rewrite the whole thing to be actually awesome (and not just pretend awesome).

## INSTALL

See INSTALL/wiki
