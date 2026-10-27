package sender

import (
	"compress/gzip"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"nazoratchi/agent/internal/metric"
)

func batch() metric.Batch {
	return metric.Batch{
		BatchID: "b-1", Seq: 7,
		Samples: []metric.Sample{{N: "load1", T: 1, V: 0.5}},
		Facts:   map[string]any{"hostname": "x"},
	}
}

func newSender(t *testing.T, url string) *Sender {
	t.Helper()
	s, err := New(url, "agt_secret", "9.9.9", "", 2*time.Second)
	if err != nil {
		t.Fatal(err)
	}
	return s
}

func TestSendPostsGzipJSONWithAuthAndFreshSentAt(t *testing.T) {
	var got metric.Batch
	var hdr http.Header
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hdr = r.Header.Clone()
		zr, err := gzip.NewReader(r.Body)
		if err != nil {
			t.Error(err)
			return
		}
		raw, _ := io.ReadAll(zr)
		_ = json.Unmarshal(raw, &got)
		_, _ = w.Write([]byte(`{"ok":true,"accepted":1,"rejected":0,"server_time":"2026-10-27T10:00:00.000Z","interval_seconds":15,"commands":[{"type":"set_interval","collector":"docker","seconds":60}]}`))
	}))
	defer srv.Close()

	res := newSender(t, srv.URL).Send(context.Background(), batch())
	if res.Outcome != OK || res.Resp.Accepted != 1 || len(res.Resp.Commands) != 1 {
		t.Fatalf("natija: %+v", res)
	}
	if hdr.Get("Authorization") != "Bearer agt_secret" || hdr.Get("Content-Encoding") != "gzip" {
		t.Fatalf("sarlavhalar: %v", hdr)
	}
	if hdr.Get("X-Nazoratchi-Agent") != "nazoratchi-agent/9.9.9" {
		t.Fatalf("agent sarlavhasi: %v", hdr.Get("X-Nazoratchi-Agent"))
	}
	if got.BatchID != "b-1" || got.Seq != 7 || !strings.HasSuffix(got.SentAt, "Z") || len(got.SentAt) != 24 {
		t.Fatalf("paket: %+v", got)
	}
}

func TestSendClassifiesStatuses(t *testing.T) {
	cases := []struct {
		status  int
		header  string
		outcome Outcome
		retry   time.Duration
	}{
		{400, "", Drop, 0},
		{413, "", Drop, 0},
		{401, "", Retry, 0},
		{403, "", Retry, 0},
		{429, "7", Retry, 7 * time.Second},
		{429, "", Retry, 30 * time.Second},
		{500, "", Retry, 0},
		{503, "", Retry, 0},
	}
	for _, c := range cases {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if c.header != "" {
				w.Header().Set("Retry-After", c.header)
			}
			w.WriteHeader(c.status)
		}))
		res := newSender(t, srv.URL).Send(context.Background(), batch())
		srv.Close()
		if res.Outcome != c.outcome || res.RetryAfter != c.retry || res.Status != c.status {
			t.Errorf("%d: %+v", c.status, res)
		}
	}
}

func TestSendNetworkErrorIsRetryAndNeverLeaksToken(t *testing.T) {
	srv := httptest.NewServer(http.NotFoundHandler())
	url := srv.URL
	srv.Close()
	res := newSender(t, url).Send(context.Background(), batch())
	if res.Outcome != Retry || res.Status != 0 {
		t.Fatalf("natija: %+v", res)
	}
	if strings.Contains(res.Detail, "agt_secret") {
		t.Fatal("token xato matniga tushdi")
	}
}

func TestSendDoesNotFollowRedirects(t *testing.T) {
	hit := false
	other := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { hit = true }))
	defer other.Close()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, other.URL, http.StatusTemporaryRedirect)
	}))
	defer srv.Close()
	res := newSender(t, srv.URL).Send(context.Background(), batch())
	if hit || res.Outcome != Retry {
		t.Fatalf("yo'naltirishga ergashilmasligi kerak: hit=%v %+v", hit, res)
	}
}

func TestStoredRoundTripDropsSentAt(t *testing.T) {
	b := batch()
	b.SentAt = "2020-01-01T00:00:00.000Z"
	data, err := EncodeStored(b)
	if err != nil {
		t.Fatal(err)
	}
	back, err := DecodeStored(data)
	if err != nil {
		t.Fatal(err)
	}
	if back.SentAt != "" || back.BatchID != "b-1" || back.Seq != 7 || len(back.Samples) != 1 || back.Facts["hostname"] != "x" {
		t.Fatalf("round-trip: %+v", back)
	}
	if _, err := DecodeStored([]byte("garbage")); err == nil {
		t.Fatal("buzuq fayl xato berishi kerak")
	}
}

func TestEnroll(t *testing.T) {
	var req map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewDecoder(r.Body).Decode(&req)
		if req["enroll_token"] == "enr_used" {
			w.WriteHeader(409)
			_, _ = w.Write([]byte(`{"error":{"code":"host_already_enrolled","message":"x","request_id":"r"}}`))
			return
		}
		_, _ = w.Write([]byte(`{"host_id":"h-1","agent_token":"agt_new","interval_seconds":15}`))
	}))
	defer srv.Close()

	res, err := Enroll(context.Background(), srv.URL, "", 2*time.Second, "enr_ok", "1.0", map[string]any{"hostname": "vm1"})
	if err != nil || res.AgentToken != "agt_new" || res.HostID != "h-1" {
		t.Fatalf("%+v %v", res, err)
	}
	if req["hostname"] != "vm1" || req["agent_version"] != "1.0" {
		t.Fatalf("so'rov: %v", req)
	}

	_, err = Enroll(context.Background(), srv.URL, "", 2*time.Second, "enr_used", "1.0", nil)
	ee, ok := err.(*EnrollError)
	if !ok || ee.Code != "host_already_enrolled" || ee.Status != 409 {
		t.Fatalf("xato: %v", err)
	}
}

func TestEnrollMalformedAndUnreachable(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"host_id":"h"}`))
	}))
	if _, err := Enroll(context.Background(), srv.URL, "", time.Second, "enr", "1", nil); err == nil || !strings.Contains(err.Error(), "javob noto'g'ri") {
		t.Fatalf("xato kutilgan: %v", err)
	}
	url := srv.URL
	srv.Close()
	if _, err := Enroll(context.Background(), url, "", time.Second, "enr_tok", "1", nil); err == nil || strings.Contains(err.Error(), "enr_tok") {
		t.Fatalf("ulanish xatosi va token oshkor bo'lmasligi: %v", err)
	}
}

func TestBadCAFile(t *testing.T) {
	if _, err := New("https://x", "t", "1", "/yoq/ca.pem", time.Second); err == nil {
		t.Fatal("ca_file yo'q bo'lsa xato kerak")
	}
}

func TestGoodbye(t *testing.T) {
	var gotAuth, gotPath, gotMethod string
	status := http.StatusOK
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth, gotPath, gotMethod = r.Header.Get("Authorization"), r.URL.Path, r.Method
		w.WriteHeader(status)
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	defer srv.Close()

	if err := Goodbye(context.Background(), srv.URL, "", "agt_secret", "1.0.0"); err != nil {
		t.Fatal(err)
	}
	if gotMethod != http.MethodPost || gotPath != "/ingest/v1/goodbye" || gotAuth != "Bearer agt_secret" {
		t.Fatalf("noto'g'ri so'rov: %s %s %q", gotMethod, gotPath, gotAuth)
	}

	status = http.StatusUnauthorized
	err := Goodbye(context.Background(), srv.URL, "", "agt_secret", "1.0.0")
	if err == nil || !strings.Contains(err.Error(), "401") {
		t.Fatalf("401 xato bo'lishi kerak: %v", err)
	}
}

func TestGoodbyeNetworkErrorHidesToken(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
	url := srv.URL
	srv.Close()
	err := Goodbye(context.Background(), url, "", "agt_secret", "1.0.0")
	if err == nil || strings.Contains(err.Error(), "agt_secret") {
		t.Fatalf("xato bo'lishi va token oshkor bo'lmasligi kerak: %v", err)
	}
}
