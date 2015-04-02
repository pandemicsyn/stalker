package runner

import (
	"crypto/tls"
	"encoding/json"
	"errors"
	"fmt"
	r "github.com/dancannon/gorethink"
	"github.com/garyburd/redigo/redis"
	"github.com/pandemicsyn/stalker/tempgo/stalker"
	"io/ioutil"
	"log"
	"net/http"
	"time"
)

type StalkerRunner struct {
	conf  string
	rpool *redis.Pool
	rsess *r.Session
}

type StalkerRunnerOpts struct {
	Conf              string
	RedisAddr         string
	RethinkConnection *r.Session
}

const (
	hostWindow     = 60
	hostThreshold  = 5
	floodWindow    = 120
	floodThreshold = 100
	flapWindow     = 1200
	flapThreshold  = 5
	alertThreshold = 3
	workerQueue    = "worker1"
	checkKey       = "canhazstatus"
)

func newRedisPool(server string) *redis.Pool {
	return &redis.Pool{
		MaxIdle:     3,
		IdleTimeout: 60 * time.Second,
		Dial: func() (redis.Conn, error) {
			c, err := redis.Dial("tcp", server)
			if err != nil {
				return nil, err
			}
			/*
			   if _, err := c.Do("AUTH", password); err != nil {
			       c.Close()
			       return nil, err
			   } */
			return c, err
		},
	}
}

func New(conf string, opts StalkerRunnerOpts) *StalkerRunner {
	sr := &StalkerRunner{conf: conf, rpool: newRedisPool(opts.RedisAddr), rsess: opts.RethinkConnection}
	return sr
}

// Start runner loop
func (sr *StalkerRunner) Start() {
	//TODO: include shutdown chan
	for {
		log.Println("Runner...running")
		time.Sleep(5 * time.Second)
		checks := sr.getChecks(1024, 5)
		log.Printf("Got checks: %v\n", checks)
		for _, v := range checks {
			log.Println("checking", v.Check)
			go sr.runCheck(v)
		}
	}

}

func (sr *StalkerRunner) loadNotificationPlugins() {
	log.Println("load notification plugins")
}

func (sr *StalkerRunner) getChecks(maxChecks int, timeout int) []stalker.StalkerCheck {
	checks := make([]stalker.StalkerCheck, 0)
	expireTime := time.Now().Add(1 * time.Second).Unix()
	for len(checks) <= maxChecks {
		//log.Println("trying to grab another", time.Now().Unix(), expireTime, len(checks), maxChecks)
		//we've got at least 1 check and exceeded our try time
		if len(checks) > 0 && time.Now().Unix() > expireTime {
			break
		}
		rconn := sr.rpool.Get()
		defer rconn.Close()
		res, err := redis.Values(rconn.Do("BLPOP", workerQueue, timeout))
		if err != nil {
			if err != redis.ErrNil {
				log.Println("Error grabbing check from queue:", err.Error())
				break
			} else {
				continue
			}
		}
		var rb []byte
		res, err = redis.Scan(res, nil, &rb)
		var check stalker.StalkerCheck
		if err := json.Unmarshal(rb, &check); err != nil {
			log.Println("Error decoding check from queue to json:", err.Error())
			break
		}
		checks = append(checks, check)
	}
	return checks
}

// TODO: Need to set deadlines
func (sr *StalkerRunner) execCheck(url string) (map[string]stalker.CheckOutput, error) {
	tr := &http.Transport{
		TLSClientConfig:     &tls.Config{InsecureSkipVerify: true},
		TLSHandshakeTimeout: 10 * time.Second,
	}
	client := &http.Client{Transport: tr, Timeout: 10 * time.Second}
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return map[string]stalker.CheckOutput{}, err
	}
	req.Header.Add("X-CHECK-KEY", checkKey)

	res, err := client.Do(req)
	if err != nil {
		return map[string]stalker.CheckOutput{}, err
	}
	defer res.Body.Close()
	if res.StatusCode != 200 {
		return map[string]stalker.CheckOutput{}, errors.New(fmt.Sprintf("Got non 200 from agent: %d|%s", res.StatusCode, res.Status))
	}
	body, err := ioutil.ReadAll(res.Body)
	if err != nil {
		return map[string]stalker.CheckOutput{}, err
	}
	var data map[string]stalker.CheckOutput
	err = json.Unmarshal(body, &data)
	if err != nil {
		log.Println("unable to decode check result", err.Error())
		log.Printf("%s", body)
		return map[string]stalker.CheckOutput{}, err
	}
	return data, nil
}

func (sr *StalkerRunner) flapIncr(flapId string) {
	log.Println("flap incr")
	rconn := sr.rpool.Get()
	defer rconn.Close()
	rconn.Send("MULTI")
	rconn.Send("INCR", flapId)
	rconn.Send("EXPIRE", flapId, flapWindow)
	_, err := rconn.Do("EXEC")
	stalker.OnlyLogIf(err)
}

func (sr *StalkerRunner) logStateChange(check stalker.StalkerCheck) {
	log.Println("log state change")
	query := stalker.StateLogEntry{
		Hostname: check.Hostname,
		Check:    check.Check,
		Cid:      check.ID,
		Status:   check.Status,
		Last:     check.Last,
		Out:      check.Out,
		Owner:    check.Owner,
	}
	_, err := r.Db("stalkerweb").Table("state_log").Insert(query).RunWrite(sr.rsess)
	if err != nil {
		log.Println("Error inserting state log entry:", err.Error())
		return
	}
}

func (sr *StalkerRunner) HostNotificationCount(hostname string) (int, error) {
	log.Println("host notification count")
	var count int
	cursor, err := r.Db("stalkerweb").Table("notifications").Filter(map[string]string{"hostname": hostname}).Count().Run(sr.rsess)
	if err != nil {
		log.Println("Can't count notifications for", hostname, "because:", err.Error())
		return 0, err
	}
	defer cursor.Close()
	err = cursor.One(&count)
	if err != nil {
		log.Println("Can't count notifications for", hostname, "because:", err.Error())
		return 0, nil
	}
	return count, nil
}

func (sr *StalkerRunner) HostFlood(hostname string) bool {
	log.Println("host flood")
	var count int
	cursor, err := r.Db("stalkerweb").Table("notifications").Filter(r.Row.Field("hostname").Eq(hostname).And(r.Row.Field("ts").Gt(int64(time.Now().Unix() - hostWindow)))).Count().Run(sr.rsess)
	if err != nil {
		log.Println("Can't do host flood count for", hostname, "because:", err.Error())
		return false
	}
	defer cursor.Close()
	err = cursor.One(&count)
	if err != nil {
		log.Println("Can't do host flood count for", hostname, "because:", err.Error())
		return false
	}
	if count > hostThreshold {
		log.Println("Host flood detected. Suppressing alerts for", hostname)
		return true
	}
	return false
}

func (sr *StalkerRunner) GlobalFlood() bool {
	log.Println("global flood")
	var count int
	cursor, err := r.Db("stalkerweb").Table("notifications").Filter(r.Row.Field("ts").Gt(int64(time.Now().Unix() - floodWindow))).Count().Run(sr.rsess)
	if err != nil {
		log.Println("Can't do global flood count because:", err.Error())
		return false
	}
	defer cursor.Close()
	err = cursor.One(&count)
	if err != nil {
		log.Println("Can't do global flood count because:", err.Error())
		return false
	}
	if count > floodThreshold {
		log.Println("Global alert flood detected. Suppressing alerts.")
		return true
	}
	return false
}

func (sr *StalkerRunner) Flapping(flapId string) bool {
	rconn := sr.rpool.Get()
	defer rconn.Close()
	count, err := redis.Int(rconn.Do("GET", flapId))
	if err != nil {
		if err != redis.ErrNil {
			log.Println("Redis error while checking", flapId, " flap state:", err.Error())
		}
	}
	log.Println(flapId, count)
	if count >= flapThreshold {
		return true
	} else {
		return false
	}
}

func (sr *StalkerRunner) emitFail(check stalker.StalkerCheck) {
	log.Println("emit fail")
}

func (sr *StalkerRunner) emitClear() {
	log.Println("emit clear")
}

func (sr *StalkerRunner) CheckFailed(check stalker.StalkerCheck) {
	log.Println("check failed")
	query := map[string]string{"hostname": check.Hostname, "check": check.Check}
	cursor, err := r.Db("stalkerweb").Table("notifications").Filter(query).Run(sr.rsess)
	if err != nil {
		log.Println("Error checking for existing notification:", err.Error())
		return
	}
	defer cursor.Close()
	result := stalker.StalkerNotification{}
	cursor.One(&result)
	if result.Active {
		log.Println("Notification already exists")
		return
	}
	log.Println("Using", check)
	query2 := stalker.StalkerNotification{
		Cid:      check.ID,
		Hostname: check.Hostname,
		Check:    check.Check,
		Ts:       time.Now().Unix(),
		Cleared:  false,
		Active:   true,
	}
	_, err = r.Db("stalkerweb").Table("notifications").Insert(query2).RunWrite(sr.rsess)
	if err != nil {
		log.Println("Error inserting notification entry:", err.Error())
		return
	}
	if sr.HostFlood(check.Hostname) != true && sr.GlobalFlood() != true {
		sr.emitFail(check)
	}
	return
}

func (sr *StalkerRunner) CheckCleared(check stalker.StalkerCheck) {
	log.Println("check cleared")
	query := map[string]string{"hostname": check.Hostname, "check": check.Check}
	cursor, err := r.Db("stalkerweb").Table("notifications").Filter(query).Run(sr.rsess)
	if err != nil {
		log.Println("Error checking for existing notification:", err.Error())
		return
	}
	defer cursor.Close()
	result := stalker.StalkerNotification{}
	cursor.One(&result)
	if result.Active == false {
		log.Println("No notification to clear")
		return
	}
	_, err = r.Db("stalkerweb").Table("notifications").Filter(query).Delete().RunWrite(sr.rsess)
	if err != nil {
		log.Println("Error deleting notification entry:", err.Error())
		return
	}
	sr.emitClear()
	return

}

func (sr *StalkerRunner) emitHostFloodAlert() {
	log.Println("emit host flood alert")
}

func (sr *StalkerRunner) emitFloodAlert() {
	log.Println("emit flood alert")
}

func (sr *StalkerRunner) StateHasChanged(check stalker.StalkerCheck, previousStatus bool) bool {
	log.Println("ps:", previousStatus)
	if check.Status != previousStatus {
		log.Println("state changed", check.Hostname, check.Check)
		sr.logStateChange(check)
		//statsd.counter('state_change')
		return true
	}
	log.Println("state unchanged:", check.Hostname, check.Check)
	return false
}

func (sr *StalkerRunner) stateChange(check stalker.StalkerCheck, previousStatus bool) {
	stateChanged := sr.StateHasChanged(check, previousStatus)
	if check.Status == true && stateChanged == true {
		sr.CheckCleared(check)
	} else if check.Status == false {
		// we don't check if stateChanged to allow for alert escalations at a later date.
		// in the mean time this means checkFailed gets called everytime a check is run and fails.
		log.Printf("%s:%s failure # %d\n", check.Hostname, check.Check, check.FailCount)
		if check.Flapping {
			log.Printf("%s:%sis flapping - skipping fail/clear\n", check.Hostname, check.Check)
			// TODO: emit flap notifications
		} else if check.FailCount >= alertThreshold {
			sr.CheckFailed(check)
		}
	}
}

func (sr *StalkerRunner) runCheck(check stalker.StalkerCheck) {
	log.Println("run check")
	var err error
	name := check.Check
	flapid := fmt.Sprintf("flap:%s:%s", check.Hostname, check.Check)
	previousStatus := check.Status
	var result map[string]stalker.CheckOutput
	result, err = sr.execCheck(fmt.Sprintf("https://%s:5050/%s", check.Ip, name))
	if err != nil {
		result = map[string]stalker.CheckOutput{name: stalker.CheckOutput{Status: 2, Out: "", Err: err.Error()}}
		// TODO: statsd.counter("checks.error")
	}
	if _, ok := result[name]; !ok {
		result = map[string]stalker.CheckOutput{name: stalker.CheckOutput{Status: 2, Out: "", Err: fmt.Sprintf("%s not in agent result", name)}}
	}
	var updatedCheck stalker.StalkerCheck
	if result[name].Status == 0 {
		if previousStatus == false {
			sr.flapIncr(flapid)
		}
		updatedCheck = check
		updatedCheck.Pending = false
		updatedCheck.Status = true
		updatedCheck.Flapping = sr.Flapping(flapid)
		updatedCheck.Next = time.Now().Unix() + int64(check.Interval)
		updatedCheck.Last = time.Now().Unix()
		updatedCheck.Out = result[name].Out + result[name].Err
		updatedCheck.FailCount = 0
		// TODO: statsd.counter("checks.passed")
		query := r.Db("stalkerweb").Table("checks").Get(check.ID).Update(updatedCheck)
		_, err := query.RunWrite(sr.rsess)
		if err != nil {
			log.Println("Can't update check on pass:", err.Error())
			return
		}
	} else {
		if previousStatus == true {
			sr.flapIncr(flapid)
		}
		updatedCheck = check
		updatedCheck.Pending = false
		updatedCheck.Status = false
		updatedCheck.Flapping = sr.Flapping(flapid)
		updatedCheck.Next = time.Now().Unix() + check.FollowUp
		updatedCheck.Last = time.Now().Unix()
		updatedCheck.Out = result[name].Out + result[name].Err
		updatedCheck.FailCount = check.FailCount + 1
		// TODO: statsd.counter("checks.failed")
		query := r.Db("stalkerweb").Table("checks").Get(check.ID).Update(updatedCheck)
		_, err := query.RunWrite(sr.rsess)
		if err != nil {
			log.Println("Can't update check on failure:", err.Error())
			return
		}
	}
	sr.stateChange(updatedCheck, previousStatus)
}
