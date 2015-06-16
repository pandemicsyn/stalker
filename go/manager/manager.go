package manager

import (
	//"fmt"
	"encoding/json"
	"sync"
	"time"

	log "github.com/Sirupsen/logrus"
	r "github.com/dancannon/gorethink"
	"github.com/garyburd/redigo/redis"
	"github.com/pandemicsyn/stalker/go/stalker"
)

const (
	// STALKERDB holds the Rethinkdb db name to use.
	STALKERDB = "stalker"
)

type Manager struct {
	rpool                  *redis.Pool
	rsess                  *r.Session
	pauseFile              string
	shuffleT               int
	scanInterval           time.Duration
	notificationExpiration int64
	stopChan               chan bool
	swg                    *sync.WaitGroup
}

// Opts config options for the manager.
type Opts struct {
	RedisAddr              string
	RethinkConnection      *r.Session
	PauseFilePath          string
	ShuffleTime            int
	ScanInterval           int
	NotificationExpiration int
}

// New creates a new instance of Manager
func New(conf string, opts Opts) *Manager {
	sm := &Manager{
		rpool:                  newRedisPool(opts.RedisAddr),
		rsess:                  opts.RethinkConnection,
		pauseFile:              opts.PauseFilePath,
		shuffleT:               opts.ShuffleTime,
		scanInterval:           time.Duration(opts.ScanInterval) * time.Second,
		notificationExpiration: int64(opts.NotificationExpiration),
		stopChan:               make(chan bool),
		swg:                    &sync.WaitGroup{},
	}
	sm.swg.Add(1)
	return sm
}

func newRedisPool(server string) *redis.Pool {
	return &redis.Pool{
		MaxIdle:     3,
		IdleTimeout: 60 * time.Second,
		Dial: func() (redis.Conn, error) {
			c, err := redis.Dial("tcp", server)
			if err != nil {
				return nil, err
			}
			return c, err
		},
	}
}

// Start the manager loop.
func (sm *Manager) Start() {
	defer sm.swg.Done()
	sm.Sanitize(false)
	sm.startupShuffle()
	for {
		select {
		case <-sm.stopChan:
			return
		default:
		}
		sm.scanChecks()
		sm.expireNotifications()
		time.Sleep(sm.scanInterval)
	}
}

// Stop the manager.
func (sm *Manager) Stop() {
	close(sm.stopChan)
	log.Warningln("manager shutting down")
	sm.swg.Wait()
}

// randomly reshuffle all checks that need to be done right now and schedule
// them for a future time. i.e. if the stalker-manager was offline
// for an extended period of time.
// TODO: y u no actually shuffle!
// TODO: optomize Get & Update
func (sm *Manager) startupShuffle() {
	log.Debugln("Reshuffling checks")
	var err error
	rquery := r.Db(STALKERDB).Table("checks").Between(0, time.Now().Unix(), r.BetweenOpts{Index: "next", RightBound: "closed"})
	cursor, err := rquery.Run(sm.rsess)
	defer cursor.Close()
	if err != nil {
		log.Panic(err)
	}

	result := stalker.Check{}

	for cursor.Next(&result) {
		_, err := r.Db(STALKERDB).Table("checks").Get(result.ID).Update(map[string]int{"next": int(time.Now().Unix()) + stalker.RandIntInRange(1, sm.shuffleT)}).RunWrite(sm.rsess)
		stalker.OnlyLogIf(err)
	}

	stalker.OnlyLogIf(cursor.Err())
}

// Check if pause file exists and sleep until its removed if it does
func (sm *Manager) pauseIfAsked() {
	if stalker.FExists(sm.pauseFile) {
		log.Warningln("Pausing")
		for {
			time.Sleep(1 * time.Second)
			if !stalker.FExists(sm.pauseFile) {
				return
			}
		}
	}
}

func (sm *Manager) queueLength() int {
	rconn := sm.rpool.Get()
	defer rconn.Close()
	n, err := redis.Int(rconn.Do("LLEN", "worker1"))
	if err != nil {
		log.Panic(err)
	}
	return n
}

// place a check on the queue
func (sm *Manager) enqueueCheck(check stalker.Check) {
	cb, err := json.Marshal(check)
	stalker.OnlyLogIf(err)
	rconn := sm.rpool.Get()
	defer rconn.Close()
	res, err := rconn.Do("RPUSH", "worker1", cb)
	log.Debugln("Checks now on queue:", res)
	if err != nil {
		log.Warningln("error pushing check on queue:", err)
	}
}

// Sanitize scan the checks db for checks marked pending but not actually
// in progress. i.e. redis died, or services where kill -9'd.
func (sm *Manager) Sanitize(flushQueued bool) {
	if flushQueued {
		rconn := sm.rpool.Get()
		defer rconn.Close()
		_, err := rconn.Do("DEL", "worker1")
		stalker.OnlyLogIf(err)
	}
	log.Debugln("Sanatizing DB")
	rquery := r.Db(STALKERDB).Table("checks").Filter(r.Row.Field("pending").Eq(true))
	rquery = rquery.Update(map[string]bool{"pending": false})
	res, err := rquery.RunWrite(sm.rsess)
	if err != nil {
		log.Panic(err)
	}
	log.Debugln(res)
}

// scan the notifications db for checks older than our expiration time and remove them. This will allow them be re-alerted on.
func (sm *Manager) expireNotifications() {
	log.Debugln("Expiring notifications")
	err := r.Db(STALKERDB).Table("notifications").Filter(r.Row.Field("ts").Lt(time.Now().Unix() - sm.notificationExpiration)).Delete().Exec(sm.rsess)
	if err != nil {
		log.Errorln("Error deleting expired notifications:", err.Error())
	}
}

// scan the checks db for checks that need to run
// mark them as pending and then drop'em on the q for the runner.
func (sm *Manager) scanChecks() {
	sm.pauseIfAsked()
	log.Debugln("Scanning for checks past due")
	qcount := 0
	rquery := r.Db(STALKERDB).Table("checks").Between(0, time.Now().Unix(), r.BetweenOpts{Index: "next", RightBound: "closed"})
	rquery = rquery.Filter(r.Row.Field("pending").Eq(false).And(r.Row.Field("suspended").Eq(false)))
	cursor, err := rquery.Run(sm.rsess)
	if err != nil {
		log.Errorln("Error scanning check db!")
		log.Errorln(err)
		return
	}
	defer cursor.Close()
	result := stalker.Check{}
	for cursor.Next(&result) {
		_, err := r.Db(STALKERDB).Table("checks").Get(result.ID).Update(map[string]bool{"pending": true}).RunWrite(sm.rsess)
		stalker.OnlyLogIf(err)
		sm.enqueueCheck(result)
		qcount++
	}
	stalker.OnlyLogIf(cursor.Err())
	log.Debugln("Queued:", qcount)
}
