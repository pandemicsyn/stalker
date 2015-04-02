package manager

import (
	//"fmt"
	"encoding/json"
	r "github.com/dancannon/gorethink"
	"github.com/garyburd/redigo/redis"
	"github.com/pandemicsyn/stalker/go/stalker"
	"log"
	"time"
)

type StalkerManager struct {
	conf      string
	rconn     redis.Conn
	rsess     *r.Session
	pauseFile string
	shuffleT  int
}

type StalkerManagerOpts struct {
	RedisConnection redis.Conn
	RethinkSession  *r.Session
	PauseFilePath   string
	ShuffleTime     int
}

func New(conf string, opts StalkerManagerOpts) *StalkerManager {
	sm := &StalkerManager{conf: conf, rconn: opts.RedisConnection, rsess: opts.RethinkSession, pauseFile: opts.PauseFilePath, shuffleT: opts.ShuffleTime}
	return sm
}

// Start the manager loop
func (sm *StalkerManager) Start() {
	//TODO: need to add controlling channels for shutdown
	sm.Sanitize(false)
	sm.startupShuffle()
	for {
		sm.scanChecks()
		//sm.expireNotifications()
		time.Sleep(2 * time.Second)
	}
}

// randomly reshuffle all checks that need to be done right now and schedul
// them for a future time. i.e. if the stalker-manager was offline
// for an extended period of time.
// TODO: y u no actually shuffle!
// TODO: optomize Get & Update
func (sm *StalkerManager) startupShuffle() {
	log.Println("Reshuffling checks")
	var err error
	rquery := r.Db("stalkerweb").Table("checks").Between(nil, time.Now().Unix(), r.BetweenOpts{Index: "next", RightBound: "closed"})
	cursor, err := rquery.Run(sm.rsess)
	defer cursor.Close()
	if err != nil {
		log.Panic(err)
	}

	result := stalker.StalkerCheck{}

	for cursor.Next(&result) {
		_, err := r.Db("stalkerweb").Table("checks").Get(result.ID).Update(map[string]int{"next": int(time.Now().Unix()) + stalker.RandIntInRange(1, sm.shuffleT)}).RunWrite(sm.rsess)
		stalker.OnlyLogIf(err)
	}

	stalker.OnlyLogIf(cursor.Err())
}

// Check if pause file exists and sleep until its removed if it does
func (sm *StalkerManager) pauseIfAsked() {
	if stalker.FExists(sm.pauseFile) {
		log.Println("Pausing")
		for {
			time.Sleep(1 * time.Second)
			if !stalker.FExists(sm.pauseFile) {
				return
			}
		}
	}
}

func (sm *StalkerManager) queueLength() int {
	n, err := redis.Int(sm.rconn.Do("LLEN", "worker1"))
	if err != nil {
		log.Panic(err)
	}
	return n
}

// place a check on the queue
func (sm *StalkerManager) enqueueCheck(check stalker.StalkerCheck) {
	log.Println("Enqueue", check.Check)
	cb, err := json.Marshal(check)
	r, err := sm.rconn.Do("RPUSH", "worker1", cb)
	stalker.OnlyLogIf(err)
	log.Println(r)
}

// scan the checks db for checks marked pending but not actually
// in progress. i.e. redis died, or services where kill -9'd.
func (sm *StalkerManager) Sanitize(flushQueued bool) {
	if flushQueued {
		_, err := sm.rconn.Do("DEL", "worker1")
		stalker.OnlyLogIf(err)
	}
	log.Println("sanitize")
	rquery := r.Db("stalkerweb").Table("checks").Filter(r.Row.Field("pending").Eq(true))
	rquery = rquery.Update(map[string]bool{"pending": false})
	res, err := rquery.RunWrite(sm.rsess)
	if err != nil {
		log.Panic(err)
	}
	log.Println(res)
}

// scan the notifications db for checks older than our expiration time and remove them. This will allow them be re-alerted on.
func (sm *StalkerManager) expireNotifications() {
	log.Println("expire notifications")
}

// scan the checks db for checks that need to run
// mark them as pending and then drop'em on the q for the runner.
func (sm *StalkerManager) scanChecks() {
	sm.pauseIfAsked()
	//i := sm.queueLength()
	qcount := 0
	rquery := r.Db("stalkerweb").Table("checks").Between(nil, time.Now().Unix(), r.BetweenOpts{Index: "next", RightBound: "closed"})
	rquery = rquery.Filter(r.Row.Field("pending").Eq(false).And(r.Row.Field("suspended").Eq(false)))
	cursor, err := rquery.Run(sm.rsess)
	if err != nil {
		log.Println("Error scanning check db!")
		log.Println(err)
		return
	}
	defer cursor.Close()
	result := stalker.StalkerCheck{}

	for cursor.Next(&result) {
		ur, err := r.Db("stalkerweb").Table("checks").Get(result.ID).Update(map[string]bool{"pending": true}).RunWrite(sm.rsess)
		log.Println("updated: ", ur)
		stalker.OnlyLogIf(err)
		sm.enqueueCheck(result)
		qcount++
	}
	stalker.OnlyLogIf(cursor.Err())
	log.Println("Queued:", qcount)
}
