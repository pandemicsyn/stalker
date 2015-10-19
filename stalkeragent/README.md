Stalker Monitoring System - PoC
===============================

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
