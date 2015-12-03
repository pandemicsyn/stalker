Stalker Monitoring System - PoC
===============================

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
