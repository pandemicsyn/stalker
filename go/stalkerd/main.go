package main

import (
	log "github.com/Sirupsen/logrus"
	r "github.com/dancannon/gorethink"
	"github.com/garyburd/redigo/redis"
	sm "github.com/pandemicsyn/stalker/go/manager"
	sr "github.com/pandemicsyn/stalker/go/runner"
	"github.com/spf13/viper"
	"os"
	"os/signal"
	"runtime"
	"syscall"
	"time"
)

const (
	STALKERDB = "stalker"
	PauseFile = "/tmp/.sm-pause"
	ShuffleT  = 30
	// for backwards compatability with old stalker
)

var cmdArgs []string

func init() {
	cmdArgs = os.Args[1:]
}

func configureLogging(v *viper.Viper) {
	level, err := log.ParseLevel(v.GetString("log_level"))
	if err != nil {
		log.Fatalln(err)
	}
	log.SetLevel(level)

	if v.GetString("log_format") == "text" {
		log.SetFormatter(&log.TextFormatter{})
	} else if v.GetString("log_format") == "json" {
		log.SetFormatter(&log.JSONFormatter{})
	} else {
		log.Errorln("Error: log_type invalid, defaulting to text")
		log.SetFormatter(&log.TextFormatter{})
	}
	switch v.GetString("log_target") {
	case "stdout":
		log.SetOutput(os.Stdout)
	case "stderr":
		log.SetOutput(os.Stderr)
	default:
		log.Errorln("Error: log_target invalid, defaulting to Stdout")
		log.SetOutput(os.Stdout)
	}
}

func main() {
	var err error

	v := viper.New()

	//TODO: push config opts to sub packages like in runner.go
	v.SetDefault("redisaddr", "127.0.0.1:6379")
	v.SetDefault("rethinkaddr", "127.0.0.1:28015")
	v.SetDefault("rethinkkey", "password")
	v.SetDefault("rethinkdb", STALKERDB)
	v.SetDefault("manager", true)
	v.SetDefault("runner", true)
	v.SetDefault("log_level", "info")
	v.SetDefault("log_format", "text")
	v.SetDefault("log_target", "stdout")
	v.SetDefault("max_procs", 1)
	v.SetDefault("notifications_expiration", 172800)

	v.SetEnvPrefix("stalker")

	v.BindEnv("redisaddr")
	v.BindEnv("rethinkaddr")
	v.BindEnv("rethinkkey")
	v.BindEnv("rethinkdb")
	v.BindEnv("manager")
	v.BindEnv("runner")
	v.BindEnv("max_procs")

	v.SetConfigName("stalkerd")
	v.AddConfigPath("/etc/stalker/")
	v.ReadInConfig()

	configureLogging(v)
	runtime.GOMAXPROCS(v.GetInt("max_procs"))

	log.Warningln("stalkerd starting up")

	var manager *sm.StalkerManager
	if v.GetBool("manager") {
		log.Warningln("starting manager")
		managerConf := sm.StalkerManagerOpts{PauseFilePath: PauseFile, ShuffleTime: ShuffleT, NotificationExpiration: v.GetInt("notifications_expiration")}
		managerConf.RedisConnection, err = redis.Dial("tcp", v.GetString("redisaddr"))
		if err != nil {
			log.Panic(err)
		}
		managerConf.ScanInterval = 2
		managerConf.RethinkSession, err = r.Connect(r.ConnectOpts{
			Address:  v.GetString("rethinkaddr"),
			Database: v.GetString("rethinkdb"),
			AuthKey:  v.GetString("rethinkkey"),
			MaxIdle:  10,
			MaxOpen:  50,
			Timeout:  5 * time.Second,
		})
		if err != nil {
			log.Panic(err)
		}
		manager = sm.New("something", managerConf)
		go manager.Start()
	}

	var runner *sr.StalkerRunner
	if v.GetBool("runner") {
		log.Warningln("starting runner")
		runnerConf := sr.StalkerRunnerOpts{}
		runnerConf.RedisAddr = v.GetString("redisaddr")
		runnerConf.ViperConf = v
		runnerConf.RethinkConnection, err = r.Connect(r.ConnectOpts{
			Address:  v.GetString("rethinkaddr"),
			Database: v.GetString("rethinkdb"),
			AuthKey:  v.GetString("rethinkkey"),
			MaxIdle:  10,
			MaxOpen:  50,
			Timeout:  5 * time.Second,
		})
		if err != nil {
			log.Panic(err)
		}

		runner = sr.New("something", runnerConf)
		go runner.Start()
	}

	ch := make(chan os.Signal)
	signal.Notify(ch, syscall.SIGINT, syscall.SIGTERM)
	log.Debugln(<-ch)
	if v.GetBool("manager") {
		manager.Stop()
	}
	if v.GetBool("runner") {
		runner.Stop()
	}

}
