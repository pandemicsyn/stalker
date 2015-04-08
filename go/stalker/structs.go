package stalker

// CheckInfo
type CheckInfo struct {
	Args     string `json:"args" gorethink:"args"`
	Cmd      string `json:"cmd" gorethink:"cmd"`
	FollowUp int64  `json:"follow_up" gorethink:"follow_up"`
	Interval int64  `json:"interval" gorethink:"interval"`
	Priority int64  `json:"priority" gorethink:"priority"`
}

// Host profile
type Host struct {
	ID       string               `json:"id,omitempty" gorethink:"id"`
	Checks   map[string]CheckInfo `json:"checks" gorethink:"checks"`
	Hostname string               `json:"hostname" gorethink:"hostname"`
	IP       string               `json:"ip" gorethink:"ip"`
	Roles    []string             `json:"roles,omitempty" gorethink:"roles,omitempty"`
}

// Check entry
type Check struct {
	ID            string `json:"id,omitempty" gorethink:"id,omitempty"`
	Status        bool   `json:"status" gorethink:"status"`
	Hostname      string `json:"hostname" gorethink:"hostname"`
	IP            string `json:"ip" gorethink:"ip"`
	InMaintenance bool   `json:"in_maintenance" gorethink:"in_maintenance"`
	Suspended     bool   `json:"suspended" gorethink:"suspended"`
	Check         string `json:"check" gorethink:"check"`
	Out           string `json:"out" gorethink:"out"`
	FollowUp      int64  `json:"follow_up" gorethink:"follow_up"`
	Last          int64  `json:"last" gorethink:"last"`
	Interval      int    `json:"interval" gorethink:"interval"`
	Next          int64  `json:"next" gorethink:"next"`
	Priority      int    `json:"priority" gorethink:"priority"`
	Pending       bool   `json:"pending" gorethink:"pending"`
	Owner         string `json:"owner,omitempty" gorethink:"owner,omitempty"`
	FailCount     int    `json:"fail_count,omitempty" gorethink:"fail_count,omitempty"`
	Flapping      bool   `json:"flapping,omitempty" gorethink:"flapping"`
}

// StateLogEntry an entry in the state_log
type StateLogEntry struct {
	Cid      string `json:"cid,omitempty" gorethink:"cid"`
	Status   bool   `json:"status" gorethink:"status"`
	Hostname string `json:"hostname" gorethink:"hostname"`
	Check    string `json:"check" gorethink:"check"`
	Out      string `json:"out" gorethink:"out"`
	Last     int64  `json:"last" gorethink:"last"`
	Owner    string `json:"owner,omitempty" gorethink:"owner,omitempty"`
}

// Notification
type Notification struct {
	Cid      string `json:"cid,omitempty" gorethink:"cid"`
	Hostname string `json:"hostname" gorethink:"hostname"`
	Check    string `json:"check" gorethink:"check"`
	Ts       int64  `json:"ts" gorethink:"ts"`
	Cleared  bool   `json:"cleared" gorethink:"cleared"`
	Active   bool   `json:"active,omitempty" gorethink:"active"`
}

// CheckOutput stores the output of a check
type CheckOutput struct {
	Err    string `json:"err"`
	Out    string `json:"out"`
	Status int    `json:"status"`
}
