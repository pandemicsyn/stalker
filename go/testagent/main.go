package main

import (
	"encoding/json"
	"net/http"
)

type AgentResponse struct {
	Name   string
	Output string
}

func CheckResponse(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	ar := AgentResponse{Name: "something", Output: "wat"}
	res, _ := json.Marshal(ar)
	w.Write(res)
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/check/something", CheckResponse)

	http.ListenAndServe(":4545", mux)
}
