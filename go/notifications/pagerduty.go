package notifications

import "github.com/stvp/pager"

func watpg() (string, error) {
	pager.ServiceKey = "something"
	incidentKey, err := pager.Trigger("Shits broke yo!")
	return incidentKey, err
}
