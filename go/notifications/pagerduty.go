package notifications

import (
	"bytes"
	"encoding/json"
	"fmt"
	log "github.com/Sirupsen/logrus"
	"github.com/pandemicsyn/stalker/go/stalker"
	"io/ioutil"
	"net/http"
)

const (
	CLIENTID = "stalkerd"
	TRIGGER  = "trigger"
	RESOLVE  = "resolve"
	URL      = "https://events.pagerduty.com/generic/2010-04-15/create_event.json"
)

type PagerDutyNotification struct {
	PriOneServiceKey  string
	PriTwoServiceKey  string
	IncidentKeyPrefix string
}

type PagerDutyEvent struct {
	ServiceKey  string               `json:"service_key"`
	EventType   string               `json:"event_type"`
	IncidentKey string               `json:"incident_key"`
	Description string               `json:"description"`
	Details     stalker.StalkerCheck `json:"details"`
	Client      string               `json:"client"`
}

func NewPagerDutyNotification(POneKey, PTwoKey, IncidentKeyPrefix string) *PagerDutyNotification {
	return &PagerDutyNotification{POneKey, PTwoKey, IncidentKeyPrefix}
}

func (pn *PagerDutyNotification) sendEvent(skey, etype, description, incidentKey string, check stalker.StalkerCheck) (string, error) {
	pde := PagerDutyEvent{
		ServiceKey:  skey,
		EventType:   etype,
		IncidentKey: incidentKey,
		Description: description,
		Details:     check,
		Client:      CLIENTID,
	}
	payload, err := json.Marshal(pde)
	if err != nil {
		return "", err
	}
	resp, err := http.Post(URL, "application/json", bytes.NewReader(payload))
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode/100 != 2 {
		body, _ := ioutil.ReadAll(resp.Body)
		return "", fmt.Errorf("Got non 2xx status: %d - %s", resp.StatusCode, body)
	}

	body, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	respJson := map[string]string{}
	err = json.Unmarshal(body, &respJson)
	if err != nil {
		return "", err
	}
	return respJson["incident_key"], nil
}

func (pn *PagerDutyNotification) Fail(check stalker.StalkerCheck) {
	incidentKey := fmt.Sprintf("%s%s:%s", pn.IncidentKeyPrefix, check.Hostname, check.Check)
	switch check.Priority {
	case 0:
		log.Debugln("Alert is priority 0. Skipping notification.")
	case 1:
		i, err := pn.sendEvent(pn.PriOneServiceKey, TRIGGER, fmt.Sprintf("%s on %s is DOWN", check.Check, check.Hostname), incidentKey, check)
		if err != nil {
			log.Errorln("Failed to trigger pager duty event:", err.Error())
			// TODO: do fallback notifications
			return
		}
		log.Infoln("Triggerd pagerduty event:", i)
	case 2:
		i, err := pn.sendEvent(pn.PriTwoServiceKey, TRIGGER, fmt.Sprintf("%s on %s is DOWN", check.Check, check.Hostname), incidentKey, check)
		if err != nil {
			log.Errorln("Failed to trigger pager duty event:", err.Error())
			// TODO: do fallback notifications
			return
		}
		log.Infoln("Triggered pagerduty event:", i)
	}
}

func (pn *PagerDutyNotification) Clear(check stalker.StalkerCheck) {
	incidentKey := fmt.Sprintf("%s%s:%s", pn.IncidentKeyPrefix, check.Hostname, check.Check)
	switch check.Priority {
	case 0:
		log.Debugln("Alert is priority 0. Skipping notification.")
	case 1:
		i, err := pn.sendEvent(pn.PriOneServiceKey, RESOLVE, fmt.Sprintf("%s on %s is UP", check.Check, check.Hostname), incidentKey, check)
		if err != nil {
			log.Errorln("Failed to resolve pager duty event:", err.Error())
			// TODO: do fallback notifications
			return
		}
		log.Infoln("Resolved pagerduty event:", i)
	case 2:
		i, err := pn.sendEvent(pn.PriTwoServiceKey, RESOLVE, fmt.Sprintf("%s on %s is UP", check.Check, check.Hostname), incidentKey, check)
		if err != nil {
			log.Errorln("Failed to resolve pager duty event:", err.Error())
			// TODO: do fallback notifications
			return
		}
		log.Infoln("Resolved pagerduty event:", i)
	}
}
