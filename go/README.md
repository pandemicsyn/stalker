Initial Line by line port to Go AND migration to rethinkdb

- not yet thorougly tested
- see TODO for ...TODO's
- lots of stuff still hard coded


## Setup

    cd stalkerd
    godep go build .
    mkdir -p /etc/stalker/stalkerd.toml
    ./stalkerd 
