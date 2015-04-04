package pagerdutynotifications

import (
//"encoding/json"
//log "github.com/Sirupsen/logrus"
//"github.com/pandemicsyn/stalker/go/stalker"
//"net/http"
)

type PagerDutyNotification struct {
	ServiceKeys       map[string]string
	IncidentKeyPrefix string
}

/*
func (pn *PagerDutyNotification) resolve(skey, description, incidentKey, check stalker.StalkerCheck) {

}

func (pn *PagerDutyNotification) Clear(check stalker.StalkerCheck) {
	incidentKey = fmt.Sprintf("%s%s:%s", pn.IncidentKeyPrefix, check.Hostname, check.Check)
	switch check.Priority {
	case 0:
		log.Println("Alert is priority 0. Skipping notification.")
	case 1:
		pager.ServiceKey = pn.ServiceKeys[1]
	}
}*/
