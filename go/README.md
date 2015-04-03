Initial Line by line port to Go AND migration to rethinkdb

- not yet thorougly tested
- see TODO for ...TODO's
- lots of stuff still hard coded
    
    cd stalkerd
    godep go build .
    STALKER_REDISADDR=127.0.0.1:49154 STALKER_RETHINKADDR=172.17.0.31:28015 ./stalkerd 
    #optionally gomaxprocs it

