## Ubuntu install

### Prereq's

Setup Rethinkdb following the instructions located at http://rethinkdb.com/docs/install/
Roughly something like:

    source /etc/lsb-release && echo "deb http://download.rethinkdb.com/apt $DISTRIB_CODENAME main" | sudo tee /etc/apt/sources.list.d/rethinkdb.list
    wget -qO- http://download.rethinkdb.com/apt/pubkey.gpg | sudo apt-key add -
    sudo apt-get update
    sudo apt-get install rethinkdb
    sudo cp /etc/rethinkdb/default.conf.sample /etc/rethinkdb/instances.d/instance1.conf
    sudo vim /etc/rethinkdb/instances.d/instance1.conf
    sudo /etc/init.d/rethinkdb restart

Install the latest version of redis available for your distro. Roughly something like:

    sudo apt-get update
    sudo apt-get install redis-server

If you will be building stalkerd, you'll need a working Go install as well. Follow the instructions located at http://golang.org/doc/install and be sure to also setup your $GOPATH. Once you have a working Go install you will need to install godep:

    go get github.com/tools/godep


### Create RethinkDB Database Tables

Before stalkerd can run, some tables must be created in RethinkDB. First
install the rethinkdb python module then run ```dbsetup.py```

	$ pip install rethinkdb
	$ cd go/packaging/root/usr/share/stalker
	$ ./dbsetup.py

If you have already set an RethinkDB Authentication Key, you can enter the
auth_key by using the ```--auth-key``` command line option
	
	$ ./dbsetup.py --auth-key
	Enter auth_key (CTRL-D to abort) > 


### Set RethinkDB Authentication Key

You should restrict rethinkdb access by setting an auth_key. See
http://rethinkdb.com/docs/security/ for more info.  To setup a password via the
command line make sure you have the rethinkdb python package installed then
run:

    import rethinkdb as r
    r.connect('localhost',28105).repl()
    r.db('rethinkdb').table('cluster_config').get('auth').update({'auth_key': 'password'}).run()
    #should return:
    #{u'skipped': 0, u'deleted': 0, u'unchanged': 0, u'errors': 0, u'replaced': 1, u'inserted': 0}​
    list(r.db('rethinkdb').table('cluster_config').run())
    #should return:
    #[{u'id': u'auth', u'auth_key': {u'hidden': True}}]

### stalker-web 

Setup stalker-web (stdeb built) and dependencies (you may wanna build in virtualenv):

    sudo apt-get install redis-server gcc python-dev
    git clone https://github.com/pandemicsyn/stalker.git
    cd stalker
    python setup.py --command-packages=stdeb.command bdist_deb
    apt-get install python-eventlet
    dpkg -i deb_dist/python-stalker_0.X.X-1_all.deb
    #alternatively setup stalker via setup.py
    #python setup.py install
    sudo pip install -r requirements.txt
    stalker-web --gen-config > /etc/stalker/stalkerweb.cfg
    stalker-web --conf=/etc/stalker/stalkerweb.cfg --init-db
    stalker-web -a <yourusername>
    #start service in debug mode
    stalker-web --conf=/etc/stalker/stalkerweb.cfg -d
    #alternatively start stalkerweb using gunicorn in daemon mode (w/ 2 workers)
    #stalker-web --conf=/etc/stalker/stalkerweb.cfg -w 2 -G

### stalkerd via deb's (repo targets trusty, should work on most anything x64)

Setup the repo

    wget -qO- http://gpgkeys.ronin.io/stalker.gpg.key | sudo apt-key add -
    echo "deb http://apt.stalker.ronin.io trusty main" | sudo tee /etc/apt/sources.list.d/stalker.list

Install the package

    sudo apt-get update
    sudo apt-get install stalkerd

### stalkerd via source

First obtain the stalker code. Since in its current configuration its not go getable

    git clone https://github.com/pandemicsyn/stalker.git $GOPATH/src/github.com/pandemicsyn/stalker
    cd $GOPATH/src/github.com/pandemicsyn/stalker
    git checkout go
    cd go

If you wish to manually build/install (like during dev) do something like:

    godep go install ./...
    mkdir -p /etc/stalker/ && cp -av packaging/root/etc/stalker/stalkerd.toml /etc/stalker
    $GOPATH/bin/stalkerd 

Or use the make file

    make build

Or better yet build .debs (if fpm is installed)

    make packages

Install the package (which also starts the service)

    dpkg -i packaging/output/stalkerd.dpkg 

Go grab a coffee, check /etc/stalker and /usr/share/stalker for sample configs, init scripts, etc.

### stalker-agent

    dpkg -i python-stalker
    apt-get install python-eventlet nagios-plugins-extra
    update-rc.d -f stalker-agent defaults
    update-rc.d -f stalker-agent enable
    sudo service stalker-agent start

###Logs

Check /var/log/stalker/* for info, you can also start the daemons with -f (in the foreground)
Make sure you deploy an SSL Cert and Key for stalker-agent.
For stalker-web you'll probably want to front it by nginx w/ SSL.
