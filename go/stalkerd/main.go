package main

import (
	r "github.com/dancannon/gorethink"
	"github.com/garyburd/redigo/redis"
	sm "github.com/pandemicsyn/stalker/go/manager"
	sr "github.com/pandemicsyn/stalker/go/runner"
	//"github.com/pandemicsyn/stalker/tempgo/stalker"
	"github.com/spf13/viper"
	"log"
	"os"
	"os/signal"
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

func main() {
	var err error

	log.Println(cmdArgs)

	viper.SetDefault("redisaddr", "127.0.0.1:6379")
	viper.SetDefault("rethinkaddr", "127.0.0.1:28015")
	viper.SetDefault("rethinkkey", "password")
	viper.SetDefault("rethinkdb", "stalkerweb")
	viper.SetDefault("manager", true)
	viper.SetDefault("runner", true)

	viper.SetEnvPrefix("stalker")

	viper.BindEnv("redisaddr")
	viper.BindEnv("rethinkaddr")
	viper.BindEnv("rethinkkey")
	viper.BindEnv("rethinkdb")
	viper.BindEnv("manager")
	viper.BindEnv("runner")

	viper.SetConfigName("stalkerd")
	viper.AddConfigPath("/etc/stalker/")
	viper.ReadInConfig()

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
