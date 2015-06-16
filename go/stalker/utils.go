package stalker

import (
	"math/rand"
	"os"
	"time"

	log "github.com/Sirupsen/logrus"
)

// FExists true if a file or dir exists
func FExists(name string) bool {
	if _, err := os.Stat(name); os.IsNotExist(err) {
		return false
	}
	return true
}

// RandIntInRange returns a random int within provided range
func RandIntInRange(min, max int) int {
	rand.Seed(time.Now().UnixNano())
	return rand.Intn(max-min) + min
}

// OnlyLogIf ...for when you wanna log an error but don't actually care
func OnlyLogIf(err error) {
	if err != nil {
		log.Errorln(err)
	}
}
