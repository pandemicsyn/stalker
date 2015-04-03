package notifications

import (
	"github.com/mailgun/mailgun-go"
)

func Wat() (string, error) {
	mg := mailgun.NewMailgun("somedomain", "somekey", "somepubkey")
	m := mg.NewMessage("test <test@test.com", "test", "test message", "test@test.com")
	_, id, err := mg.Send(m)
	return id, err
}
