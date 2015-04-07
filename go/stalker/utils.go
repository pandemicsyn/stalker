package stalker

import (
	log "github.com/Sirupsen/logrus"
	"math/rand"
	"os"
	"time"
)

// true if file or dir exists
func FExists(name string) bool {
	if _, err := os.Stat(name); os.IsNotExist(err) {
		return false
	} else {
		return true
	}
}

func RandIntInRange(min, max int) int {
	rand.Seed(time.Now().Unix())
	return rand.Intn(max-min) + min
}

func OnlyLogIf(err error) {
	if err != nil {
		log.Errorln(err)
	}
}
