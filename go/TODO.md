## Stuff that definitely works
- stalker-client works fine with the flask app
- agent registration works fine with the flask app
- most api calls work fine via the flask app

## Major stuff

- Notification extensions (stick with pagerduty & mailgun initially)
- Tests

## Minor

- Statsd Stuff
- ~~fix redis pools~~
- fix open file errors (ulimit and limit max concurrent checks inflight)
- Double check flap detection 

## Ops/production stuff
    - packaging
    - ~~init scripts~~
    - syslog
    - ~~config file support~~
    - ~~start/stop/restart controlling channels~~

## New Stuff to add (possibly)
- Manager past due check
- Redis sentinal || round robin work queue
- Ditch redis queue for rethinkdb assignments and change feeds ? 

## Near term
- Oh god, the flask app, wtf was i thinking.
- start idiomatic go rewrite (i.e. replacing the line by line port)

## Inline
manager/manager.go:48:// TODO: y u no actually shuffle!
manager/manager.go:49:// TODO: optomize Get & Update
runner/runner.go:117:// TODO: Need to set deadlines
runner/runner.go:355:			// TODO: emit flap notifications
runner/runner.go:372:		// TODO: statsd.counter("checks.error")
runner/runner.go:390:		// TODO: statsd.counter("checks.passed")
runner/runner.go:409:		// TODO: statsd.counter("checks.failed")
