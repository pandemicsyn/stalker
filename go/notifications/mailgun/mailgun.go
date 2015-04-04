package MailgunNotification

import (
	"fmt"
	log "github.com/Sirupsen/logrus"
	"github.com/mailgun/mailgun-go"
	"github.com/pandemicsyn/stalker/go/stalker"
)

type MailgunNotification struct {
	Domain    string
	ApiUser   string
	ApiKey    string
	Recipient string
	FromAddr  string
}

func New(domain, apiuser, apikey, recipient, fromaddr string) *MailgunNotification {
	return &MailgunNotification{domain, apiuser, apikey, recipient, fromaddr}
}

func (mn *MailgunNotification) genMessage(check stalker.StalkerCheck) (string, error) {
	name := check.Check
	hostname := check.Hostname

	var status string
	if check.Status {
		status = "UP"
	} else {
		status = "DOWN"
	}
	subject := fmt.Sprintf("[stalker] %s on %s is %s", name, hostname, status)
	body := fmt.Sprintf("%+v", check)
	mg := mailgun.NewMailgun(mn.Domain, mn.ApiKey, "")
	m := mailgun.NewMessage(mn.FromAddr, subject, body, mn.Recipient)
	_, id, err := mg.Send(m)
	return id, err
}

func (mn *MailgunNotification) Fail(check stalker.StalkerCheck) {
	incidentKey := fmt.Sprintf("%s:%s", check.Hostname, check.Check)
	id, err := mn.genMessage(check)
	if err != nil {
		log.Println("Error generating alert via mailgun:", err.Error(), id)
		// TODO: trigger fallback notifications
		return
	}
	log.Println("Sent mailgun alert for:", incidentKey)
}

func (mn *MailgunNotification) Clear(check stalker.StalkerCheck) {
	incidentKey := fmt.Sprintf("%s:%s", check.Hostname, check.Check)
	id, err := mn.genMessage(check)
	if err != nil {
		log.Println("Error generating clear via mailgun:", err.Error(), id)
		// TODO: trigger fallback notifications
		return
	}
	log.Println("Sent mailgun clear for:", incidentKey)
}
