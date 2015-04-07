package runner

import (
	"crypto/tls"
	"encoding/json"
	"errors"
	"fmt"
	log "github.com/Sirupsen/logrus"
	r "github.com/dancannon/gorethink"
	"github.com/garyburd/redigo/redis"
	"github.com/pandemicsyn/stalker/go/notifications"
	"github.com/pandemicsyn/stalker/go/stalker"
	"github.com/spf13/viper"
	"io/ioutil"
	"net/http"
	"sync"
	"time"
)

const (
	STALKERDB = "stalker"
)

type StalkerRunner struct {
	conf           *runnerConf
	rpool          *redis.Pool
	rsess          *r.Session
	stopChan       chan bool
	swg            *sync.WaitGroup
	checkTransport *http.Transport
	checkClient    *http.Client
	twilio         *notifications.TwilioNotification
	mailgun        *notifications.MailgunNotification
	pagerduty      *notifications.PagerDutyNotification
}

type StalkerRunnerOpts struct {
	RedisAddr         string
	RethinkConnection *r.Session
	ViperConf         *viper.Viper
}

type runnerConf struct {
	checkTimeout               time.Duration
	hostWindow                 int64
	hostThreshold              int
	floodWindow                int64
	floodThreshold             int
	flapWindow                 int
	flapThreshold              int
	alertThreshold             int
	workerQueue                string
	checkKey                   string
	twilioEnabled              bool
	twsid                      string
	twtoken                    string
	twfrom                     string
	twdest                     []string
	pagerDutyEnabled           bool
	pagerDutyPriOneKey         string
	pagerDutyPriTwoKey         string
	pagerDutyIncidentKeyPrefix string
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
			/*
			   if _, err := c.Do("AUTH", password); err != nil {
			       c.Close()
			       return nil, err
			   } */
			return c, err
		},
	}
}

func loadConfig(v *viper.Viper) *runnerConf {
	v.SetDefault("check_timeout", 10)
	v.SetDefault("host_window", 60)
	v.SetDefault("host_threshold", 5)
	v.SetDefault("flood_window", 120)
	v.SetDefault("flood_threshold", 100)
	v.SetDefault("flap_window", 1200)
	v.SetDefault("flap_threshold", 5)
	v.SetDefault("alert_threshold", 3)
	v.SetDefault("worker_id", "worker1")
	v.SetDefault("check_key", "canhazstatus")
	conf := &runnerConf{}
	conf.checkTimeout = v.GetDuration("check_timeout")
	conf.hostWindow = int64(v.GetInt("host_window"))
	conf.hostThreshold = v.GetInt("host_threshold")
	conf.floodWindow = int64(v.GetInt("flood_window"))
	conf.floodThreshold = v.GetInt("flood_threshold")
	conf.flapWindow = v.GetInt("flap_window")
	conf.flapThreshold = v.GetInt("flap_threshold")
	conf.alertThreshold = v.GetInt("alert_threshold")
	conf.workerQueue = v.GetString("worker_id")
	conf.checkKey = v.GetString("check_key")

	//twilio config
	v.SetDefault("twilio_enable", false)
	conf.twilioEnabled = v.GetBool("twilio_enable")
	conf.twsid = v.GetString("twiliosid")
	conf.twtoken = v.GetString("twiliotoken")
	conf.twfrom = v.GetString("twiliofrom")
	conf.twdest = v.GetStringSlice("twiliodest")

	//pagerduty config
	v.SetDefault("pagerduty_enable", false)
	conf.pagerDutyEnabled = v.GetBool("pagerduty_enable")
	conf.pagerDutyPriOneKey = v.GetString("pagerduty_priority_one_key")
	conf.pagerDutyPriTwoKey = v.GetString("pagerduty_priority_two_key")
	conf.pagerDutyIncidentKeyPrefix = v.GetString("pagerduty_incident_key_prefix")

	return conf
}

func New(conf string, opts StalkerRunnerOpts) *StalkerRunner {
	sr := &StalkerRunner{
		conf:     loadConfig(opts.ViperConf),
		rpool:    newRedisPool(opts.RedisAddr),
		rsess:    opts.RethinkConnection,
		stopChan: make(chan bool),
		swg:      &sync.WaitGroup{},
	}
	sr.checkTransport = &http.Transport{
		TLSClientConfig:       &tls.Config{InsecureSkipVerify: true},
		TLSHandshakeTimeout:   10 * time.Second,
		MaxIdleConnsPerHost:   1,
		ResponseHeaderTimeout: 10 * time.Second,
		DisableKeepAlives:     false,
	}
	sr.checkClient = &http.Client{Transport: sr.checkTransport, Timeout: sr.conf.checkTimeout * time.Second}
	if sr.conf.twilioEnabled {
		sr.twilio = notifications.NewTwilioNotification(sr.conf.twsid, sr.conf.twtoken, sr.conf.twfrom, sr.conf.twdest)
	}
	if sr.conf.pagerDutyEnabled {
		sr.pagerduty = notifications.NewPagerDutyNotification(sr.conf.pagerDutyPriOneKey, sr.conf.pagerDutyPriTwoKey, sr.conf.pagerDutyIncidentKeyPrefix)
	}
	sr.swg.Add(1)
	return sr
}

// Start runner loop
func (sr *StalkerRunner) Start() {
	defer sr.swg.Done()
	for {
		select {
		case <-sr.stopChan:
			return
		default:
		}
		checks := sr.getChecks(1024, 2)
		for _, v := range checks {
			sr.swg.Add(1)
			go sr.runCheck(v)
		}
	}

}

func (sr *StalkerRunner) Stop() {
	close(sr.stopChan)
	log.Warn("runner shutting down")
	sr.swg.Wait()
}

func (sr *StalkerRunner) getChecks(maxChecks int, timeout int) []stalker.StalkerCheck {
	checks := make([]stalker.StalkerCheck, 0)
	expireTime := time.Now().Add(3 * time.Second).Unix()
	for len(checks) <= maxChecks {
		//we've exceeded our try time
		if time.Now().Unix() > expireTime {
			break
		}
		rconn := sr.rpool.Get()
		defer rconn.Close()
		res, err := redis.Values(rconn.Do("BLPOP", sr.conf.workerQueue, timeout))
		if err != nil {
			if err != redis.ErrNil {
				log.Errorln("Error grabbing check from queue:", err.Error())
				break
			} else {
				continue
			}
		}
		var rb []byte
		res, err = redis.Scan(res, nil, &rb)
		var check stalker.StalkerCheck
		if err := json.Unmarshal(rb, &check); err != nil {
			log.Errorln("Error decoding check from queue to json:", err.Error())
			break
		}
		checks = append(checks, check)
	}
	return checks
}

// TODO: Need to set deadlines
func (sr *StalkerRunner) execCheck(url string) (map[string]stalker.CheckOutput, error) {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return map[string]stalker.CheckOutput{}, err
	}
	req.Header.Add("X-CHECK-KEY", sr.conf.checkKey)

	res, err := sr.checkClient.Do(req)
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
		log.Errorln("unable to decode check result", err.Error())
		log.Errorf("%s", body)
		return map[string]stalker.CheckOutput{}, err
	}
	return data, nil
}

func (sr *StalkerRunner) flapIncr(flapId string) {
	rconn := sr.rpool.Get()
	defer rconn.Close()
	rconn.Send("MULTI")
	rconn.Send("INCR", flapId)
	rconn.Send("EXPIRE", flapId, sr.conf.flapWindow)
	_, err := rconn.Do("EXEC")
	stalker.OnlyLogIf(err)
}

func (sr *StalkerRunner) logStateChange(check stalker.StalkerCheck) {
	log.Debug("log state change")
	query := stalker.StateLogEntry{
		Hostname: check.Hostname,
		Check:    check.Check,
		Cid:      check.ID,
		Status:   check.Status,
		Last:     check.Last,
		Out:      check.Out,
		Owner:    check.Owner,
	}
	_, err := r.Db(STALKERDB).Table("state_log").Insert(query).RunWrite(sr.rsess)
	if err != nil {
		log.Errorln("Error inserting state log entry:", err.Error())
		return
	}
}

func (sr *StalkerRunner) HostNotificationCount(hostname string) (int, error) {
	var count int
	cursor, err := r.Db(STALKERDB).Table("notifications").Filter(map[string]string{"hostname": hostname}).Count().Run(sr.rsess)
	if err != nil {
		log.Errorln("Can't count notifications for", hostname, "because:", err.Error())
		return 0, err
	}
	defer cursor.Close()
	err = cursor.One(&count)
	if err != nil {
		log.Errorln("Can't count notifications for", hostname, "because:", err.Error())
		return 0, nil
	}
	log.Debugf("%s notification count: %d", hostname, count)
	return count, nil
}

func (sr *StalkerRunner) HostFlood(hostname string) bool {
	var count int
	cursor, err := r.Db(STALKERDB).Table("notifications").Filter(r.Row.Field("hostname").Eq(hostname).And(r.Row.Field("ts").Gt(int64(time.Now().Unix() - sr.conf.hostWindow)))).Count().Run(sr.rsess)
	if err != nil {
		log.Errorln("Can't do host flood count for", hostname, "because:", err.Error())
		return false
	}
	defer cursor.Close()
	err = cursor.One(&count)
	if err != nil {
		log.Errorln("Can't do host flood count for", hostname, "because:", err.Error())
		return false
	}
	log.Debugf("%s flood count: %d", hostname, count)
	if count > sr.conf.hostThreshold {
		log.Infoln("Host flood detected. Suppressing alerts for", hostname)
		return true
	}
	return false
}

func (sr *StalkerRunner) GlobalFlood() bool {
	log.Debug("global flood")
	var count int
	cursor, err := r.Db(STALKERDB).Table("notifications").Filter(r.Row.Field("ts").Gt(int64(time.Now().Unix() - sr.conf.floodWindow))).Count().Run(sr.rsess)
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
	log.Debugln("Global flood count:", count)
	if count > sr.conf.floodThreshold {
		log.Errorln("Global alert flood detected. Suppressing alerts.")
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
			log.Errorln("Redis error while checking", flapId, " flap state:", err.Error())
		}
	}
	log.Debugln(flapId, "flap count:", count)
	if count >= sr.conf.flapThreshold {
		return true
	} else {
		return false
	}
}

func (sr *StalkerRunner) emitFail(check stalker.StalkerCheck) {
	log.Debug("emit fail")
	if sr.conf.pagerDutyEnabled {
		sr.pagerduty.Fail(check)
	}
	if sr.conf.twilioEnabled {
		sr.twilio.Fail(check)
	}
}

func (sr *StalkerRunner) emitClear(check stalker.StalkerCheck) {
	log.Debug("emit clear")
	if sr.conf.pagerDutyEnabled {
		sr.pagerduty.Clear(check)
	}
	if sr.conf.twilioEnabled {
		sr.twilio.Clear(check)
	}
}

func (sr *StalkerRunner) CheckFailed(check stalker.StalkerCheck) {
	log.Debug("check CheckFailed")
	query := map[string]string{"hostname": check.Hostname, "check": check.Check}
	cursor, err := r.Db(STALKERDB).Table("notifications").Filter(query).Run(sr.rsess)
	if err != nil {
		log.Errorln("Error checking for existing notification:", err.Error())
		return
	}
	defer cursor.Close()
	result := stalker.StalkerNotification{}
	cursor.One(&result)
	if result.Active {
		log.Debugln("Notification already exists for", check.Hostname, check.Check)
		return
	} else {
		log.Infof("%s %s detected as failed: %s", check.Hostname, check.Check, check.Out)
	}
	query2 := stalker.StalkerNotification{
		Cid:      check.ID,
		Hostname: check.Hostname,
		Check:    check.Check,
		Ts:       time.Now().Unix(),
		Cleared:  false,
		Active:   true,
	}
	_, err = r.Db(STALKERDB).Table("notifications").Insert(query2).RunWrite(sr.rsess)
	if err != nil {
		log.Errorln("Error inserting notification entry:", err.Error())
		return
	}
	if sr.HostFlood(check.Hostname) != true && sr.GlobalFlood() != true {
		sr.emitFail(check)
	} else {
		log.Debug("Host or global flood detecting, skipping emitFail")
	}
	return
}

func (sr *StalkerRunner) CheckCleared(check stalker.StalkerCheck) {
	log.Debugln("check cleared")
	log.Infof("%s %s detected as cleared", check.Hostname, check.Check)
	query := map[string]string{"hostname": check.Hostname, "check": check.Check}
	cursor, err := r.Db(STALKERDB).Table("notifications").Filter(query).Run(sr.rsess)
	if err != nil {
		log.Errorln("Error checking for existing notification:", err.Error())
		return
	}
	defer cursor.Close()
	result := stalker.StalkerNotification{}
	cursor.One(&result)
	if result.Active == false {
		log.Infoln("No notification to clear")
		return
	}
	_, err = r.Db(STALKERDB).Table("notifications").Filter(query).Delete().RunWrite(sr.rsess)
	if err != nil {
		log.Errorln("Error deleting notification entry:", err.Error())
		return
	}
	sr.emitClear(check)
	return

}

func (sr *StalkerRunner) emitHostFloodAlert() {
	log.Println("emit host flood alert")
}

func (sr *StalkerRunner) emitFloodAlert() {
	log.Println("emit flood alert")
}

func (sr *StalkerRunner) StateHasChanged(check stalker.StalkerCheck, previousStatus bool) bool {
	if check.Status != previousStatus {
		log.Debugln("state changed", check.Hostname, check.Check)
		sr.logStateChange(check)
		//statsd.counter('state_change')
		return true
	}
	log.Debugln("state unchanged:", check.Hostname, check.Check, previousStatus)
	return false
}

func (sr *StalkerRunner) stateChange(check stalker.StalkerCheck, previousStatus bool) {
	stateChanged := sr.StateHasChanged(check, previousStatus)
	if check.Status == true && stateChanged == true {
		sr.CheckCleared(check)
	} else if check.Status == false {
		// we don't check if stateChanged to allow for alert escalations at a later date.
		// in the mean time this means checkFailed gets called everytime a check is run and fails.
		log.Infof("%s:%s failure # %d", check.Hostname, check.Check, check.FailCount)
		if check.Flapping {
			log.Infof("%s:%s is flapping - skipping fail/clear", check.Hostname, check.Check)
			// TODO: emit flap notifications
		} else if check.FailCount >= sr.conf.alertThreshold {
			sr.CheckFailed(check)
		}
	}
}

func (sr *StalkerRunner) runCheck(check stalker.StalkerCheck) {
	defer sr.swg.Done()
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
		log.Debugf("%+v", updatedCheck)

		// TODO: statsd.counter("checks.passed")
		query := r.Db(STALKERDB).Table("checks").Get(check.ID).Update(updatedCheck)
		_, err := query.RunWrite(sr.rsess)
		if err != nil {
			log.Errorln("Can't update check on pass:", err.Error())
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
		log.Debugf("%+v", updatedCheck)
		// TODO: statsd.counter("checks.failed")
		query := r.Db(STALKERDB).Table("checks").Get(check.ID).Update(updatedCheck)
		_, err := query.RunWrite(sr.rsess)
		if err != nil {
			log.Errorln("Can't update check on failure:", err.Error())
			return
		}
	}
	sr.stateChange(updatedCheck, previousStatus)
}
