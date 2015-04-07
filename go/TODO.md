## Stuff that definitely works
- stalker-client works fine with the flask app
- agent registration works fine with the flask app
- most api calls work fine via the flask app

## Major stuff

- ~~Notification extensions (stick with pagerduty & mailgun initially)~~
- Tests

## Minor

- Statsd Stuff
- ~~fix redis pools~~
- ~~fix open file errors (ulimit and limit max concurrent checks inflight)~~
- ~~Double check flap detection~~

## Ops/production stuff
    - packaging
    - ~~init scripts~~
    - syslog or file
    - ~~config file support~~
    - ~~start/stop/restart controlling channels~~

## New Stuff to add (possibly)
- Manager past due check
- Redis sentinal || round robin work queue
- Ditch redis queue for rethinkdb assignments and change feeds ? 

## Near term
- Oh god, the flask app, wtf was i thinking.
- start idiomatic go rewrite (i.e. replacing the line by line port)
- fall back notification support (i.e. if method x fails trigger y)
