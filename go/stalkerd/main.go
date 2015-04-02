package main

import (
	r "github.com/dancannon/gorethink"
	"github.com/garyburd/redigo/redis"
	sm "github.com/pandemicsyn/stalker/go/manager"
	sr "github.com/pandemicsyn/stalker/go/runner"
	//"github.com/pandemicsyn/stalker/tempgo/stalker"
	"github.com/spf13/viper"
	"log"
	"time"
)

const (
	PauseFile = "/tmp/.sm-pause"
	ShuffleT  = 30
	// for backwards compatability with old stalker
)

func main() {
	var err error

	viper.SetDefault("redisAddr", "127.0.0.1:6379")
	viper.SetDefault("rethinkAddr", "127.0.0.1:28015")
	viper.SetDefault("rethinkKey", "password")
	viper.SetDefault("rethinkDB", "stalkerweb")
	viper.SetDefault("manager", true)
	viper.SetDefault("runner", true)

	viper.SetEnvPrefix("stalker")

	viper.BindEnv("redisAddr")
	viper.BindEnv("rethinkAddr")
	viper.BindEnv("rethinkKey")
	viper.BindEnv("rethinkDB")
	viper.BindEnv("manager")
	viper.BindEnv("runner")

	log.Println("Starting up")
	if viper.GetBool("manager") {
		managerConf := sm.StalkerManagerOpts{PauseFilePath: PauseFile, ShuffleTime: ShuffleT}
		managerConf.RedisConnection, err = redis.Dial("tcp", viper.GetString("redisAddr"))
		if err != nil {
			log.Panic(err)
		}
		managerConf.RethinkSession, err = r.Connect(r.ConnectOpts{
			Address:  viper.GetString("rethinkAddr"),
			Database: viper.GetString("rethinkDB"),
			AuthKey:  viper.GetString("rethinkKey"),
			MaxIdle:  10,
			MaxOpen:  50,
			Timeout:  5 * time.Second,
		})
		if err != nil {
			log.Panic(err)
		}
		manager := sm.New("something", managerConf)
		go manager.Start()
	}

	runnerConf := sr.StalkerRunnerOpts{}
	runnerConf.RedisAddr = viper.GetString("redisAddr")
	runnerConf.RethinkConnection, err = r.Connect(r.ConnectOpts{
		Address:  viper.GetString("rethinkAddr"),
		Database: viper.GetString("rethinkDB"),
		AuthKey:  viper.GetString("rethinkKey"),
		MaxIdle:  10,
		MaxOpen:  50,
		Timeout:  5 * time.Second,
	})
	if err != nil {
		log.Panic(err)
	}

	runner := sr.New("something", runnerConf)
	runner.Start()

}
