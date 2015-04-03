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
	PauseFile = "/tmp/.sm-pause"
	ShuffleT  = 30
	// for backwards compatability with old stalker
)

var cmdArgs []string

func init() {
	cmdArgs = os.Args[1:]
}

func configureLogging() {

	level, err := log.ParseLevel(viper.GetString("log_level"))
	if err != nil {
		log.Fatalln(err)
	}
	log.SetLevel(level)

	if viper.GetString("log_format") == "text" {
		log.SetFormatter(&log.TextFormatter{})
	} else if viper.GetString("log_format") == "json" {
		log.SetFormatter(&log.JSONFormatter{})
	} else {
		log.Println("Error: log_type invalid, defaulting to text")
		log.SetFormatter(&log.TextFormatter{})
	}

	switch viper.GetString("log_target") {
	case "stdout":
		log.SetOutput(os.Stdout)
	case "stderr":
		log.SetOutput(os.Stderr)
	default:
		log.Println("Error: log_target invalid, defaulting to Stdout")
		log.SetOutput(os.Stdout)
	}
}

func main() {
	var err error

	viper.SetDefault("redisaddr", "127.0.0.1:6379")
	viper.SetDefault("rethinkaddr", "127.0.0.1:28015")
	viper.SetDefault("rethinkkey", "password")
	viper.SetDefault("rethinkdb", "stalkerweb")
	viper.SetDefault("manager", true)
	viper.SetDefault("runner", true)
	viper.SetDefault("log_level", "info")
	viper.SetDefault("log_format", "text")
	viper.SetDefault("log_target", "stdout")
	viper.SetDefault("max_procs", 1)

	viper.SetEnvPrefix("stalker")

	viper.BindEnv("redisaddr")
	viper.BindEnv("rethinkaddr")
	viper.BindEnv("rethinkkey")
	viper.BindEnv("rethinkdb")
	viper.BindEnv("manager")
	viper.BindEnv("runner")
	viper.BindEnv("max_procs")

	viper.SetConfigName("stalkerd")
	viper.AddConfigPath("/etc/stalker/")
	viper.ReadInConfig()

	configureLogging()

	runtime.GOMAXPROCS(viper.GetInt("max_procs"))

	log.Println("Starting up")

	var manager *sm.StalkerManager
	if viper.GetBool("manager") {
		log.Println("starting manager")
		managerConf := sm.StalkerManagerOpts{PauseFilePath: PauseFile, ShuffleTime: ShuffleT}
		managerConf.RedisConnection, err = redis.Dial("tcp", viper.GetString("redisaddr"))
		if err != nil {
			log.Panic(err)
		}
		managerConf.RethinkSession, err = r.Connect(r.ConnectOpts{
			Address:  viper.GetString("rethinkaddr"),
			Database: viper.GetString("rethinkdb"),
			AuthKey:  viper.GetString("rethinkkey"),
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
	if viper.GetBool("runner") {
		log.Println("starting runner")
		runnerConf := sr.StalkerRunnerOpts{}
		runnerConf.RedisAddr = viper.GetString("redisaddr")
		runnerConf.RethinkConnection, err = r.Connect(r.ConnectOpts{
			Address:  viper.GetString("rethinkaddr"),
			Database: viper.GetString("rethinkdb"),
			AuthKey:  viper.GetString("rethinkkey"),
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
	log.Println(<-ch)
	manager.Stop()
	runner.Stop()
}
