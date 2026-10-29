// Package sender — core bilan HTTPS aloqa: metrika yuborish va enroll (TZ 7.5). Token hech qachon
// logga yoki xato matniga tushmaydi.
package sender

import (
	"bytes"
	"compress/gzip"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"nazoratchi/agent/internal/metric"
)

type Outcome int

const (
	OK    Outcome = iota
	Drop          // paket yaroqsiz: navbatda qoldirilmaydi (400, 413)
	Retry         // navbatda qoladi, keyinroq qayta uriniladi
)

type Command struct {
	Type      string `json:"type"`
	Collector string `json:"collector,omitempty"`
	Seconds   int    `json:"seconds,omitempty"`
	// `update` buyrug'i (TZ 7.7.3): faqat maslahat, haqiqiy qiymatlar imzolangan reliz fayllaridan olinadi.
	Version string `json:"version,omitempty"`
	SHA256  string `json:"sha256,omitempty"`
	URL     string `json:"url,omitempty"`
}

// Response — `POST /ingest/v1/metrics` javobi (TZ 7.5.2).
type Response struct {
	OK              bool      `json:"ok"`
	Accepted        int       `json:"accepted"`
	Rejected        int       `json:"rejected"`
	Duplicate       bool      `json:"duplicate"`
	ClockSkew       bool      `json:"clock_skew"`
	ServerTime      string    `json:"server_time"`
	IntervalSeconds int       `json:"interval_seconds"`
	Commands        []Command `json:"commands"`
}

type Result struct {
	Outcome    Outcome
	Status     int // 0: tarmoq xatosi
	RetryAfter time.Duration
	Detail     string
	Resp       Response
	ReceivedAt time.Time
}

type Sender struct {
	endpoint string
	token    string
	version  string
	hc       *http.Client
	now      func() time.Time
}

func New(coreURL, token, version, caFile string, timeout time.Duration) (*Sender, error) {
	hc, err := newHTTPClient(caFile, timeout)
	if err != nil {
		return nil, err
	}
	return &Sender{
		endpoint: strings.TrimRight(coreURL, "/") + "/ingest/v1/metrics",
		token:    token, version: version, hc: hc, now: time.Now,
	}, nil
}

// NewHTTPClient core'ga so'rov uchun: sozlamadagi CA, TLS >= 1.2, yo'naltirishga ergashmaydi.
func NewHTTPClient(caFile string, timeout time.Duration) (*http.Client, error) {
	return newHTTPClient(caFile, timeout)
}

func newHTTPClient(caFile string, timeout time.Duration) (*http.Client, error) {
	tlsCfg := &tls.Config{MinVersion: tls.VersionTLS12}
	if caFile != "" {
		pem, err := os.ReadFile(caFile)
		if err != nil {
			return nil, fmt.Errorf("ca_file o'qilmadi: %w", err)
		}
		pool, err := x509.SystemCertPool()
		if err != nil || pool == nil {
			pool = x509.NewCertPool()
		}
		if !pool.AppendCertsFromPEM(pem) {
			return nil, errors.New("ca_file da yaroqli sertifikat yo'q")
		}
		tlsCfg.RootCAs = pool
	}
	return &http.Client{
		Timeout:   timeout,
		Transport: &http.Transport{TLSClientConfig: tlsCfg, Proxy: http.ProxyFromEnvironment},
		// Yo'naltirishga ergashilmaydi: token boshqa manzilga ketib qolmasin.
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
	}, nil
}

// Encode paketni gzip JSON ga o'giradi; `sent_at` har safar yangilanadi.
func Encode(b metric.Batch, now time.Time) ([]byte, error) {
	b.SentAt = now.UTC().Format("2006-01-02T15:04:05.000Z")
	return gz(b)
}

// EncodeStored navbatda saqlash uchun (sent_at siz).
func EncodeStored(b metric.Batch) ([]byte, error) {
	b.SentAt = ""
	return gz(b)
}

func gz(v any) ([]byte, error) {
	var buf bytes.Buffer
	w := gzip.NewWriter(&buf)
	if err := json.NewEncoder(w).Encode(v); err != nil {
		return nil, err
	}
	if err := w.Close(); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

// DecodeStored navbatdagi faylni paketga o'giradi.
func DecodeStored(data []byte) (metric.Batch, error) {
	var b metric.Batch
	r, err := gzip.NewReader(bytes.NewReader(data))
	if err != nil {
		return b, err
	}
	defer r.Close()
	if err := json.NewDecoder(io.LimitReader(r, 8<<20)).Decode(&b); err != nil {
		return b, err
	}
	if b.BatchID == "" {
		return b, errors.New("batch_id yo'q")
	}
	return b, nil
}

// Send paketni yuboradi va javobni TZ 7.5.2 jadvali bo'yicha tasniflaydi.
func (s *Sender) Send(ctx context.Context, b metric.Batch) Result {
	body, err := Encode(b, s.now())
	if err != nil {
		return Result{Outcome: Drop, Detail: "kodlash xatosi: " + err.Error()}
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, s.endpoint, bytes.NewReader(body))
	if err != nil {
		return Result{Outcome: Drop, Detail: "so'rov yaratilmadi"}
	}
	req.Header.Set("Authorization", "Bearer "+s.token)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Content-Encoding", "gzip")
	req.Header.Set("X-Nazoratchi-Agent", "nazoratchi-agent/"+s.version)

	resp, err := s.hc.Do(req)
	if err != nil {
		return Result{Outcome: Retry, Detail: redact(err, s.token)}
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	res := Result{Status: resp.StatusCode, ReceivedAt: s.now()}

	switch {
	case resp.StatusCode == http.StatusOK:
		res.Outcome = OK
		if err := json.Unmarshal(raw, &res.Resp); err != nil {
			res.Detail = "javob JSON emas"
		}
	case resp.StatusCode == http.StatusBadRequest, resp.StatusCode == http.StatusRequestEntityTooLarge:
		res.Outcome, res.Detail = Drop, "HTTP "+strconv.Itoa(resp.StatusCode)
	case resp.StatusCode == http.StatusTooManyRequests:
		res.Outcome, res.Detail = Retry, "HTTP 429"
		res.RetryAfter = 30 * time.Second
		if secs, err := strconv.Atoi(resp.Header.Get("Retry-After")); err == nil && secs > 0 {
			res.RetryAfter = time.Duration(secs) * time.Second
		}
	default:
		res.Outcome, res.Detail = Retry, "HTTP "+strconv.Itoa(resp.StatusCode)
	}
	return res
}

func redact(err error, token string) string {
	msg := err.Error()
	if token != "" {
		msg = strings.ReplaceAll(msg, token, "***")
	}
	return msg
}

// ---- enroll (TZ 7.5.1) ----

type EnrollResult struct {
	HostID          string `json:"host_id"`
	AgentToken      string `json:"agent_token"`
	IntervalSeconds int    `json:"interval_seconds"`
}

// EnrollError core javobidagi xato kodi (`invalid_enroll_token`, `enroll_token_expired`, ...).
type EnrollError struct {
	Code   string
	Status int
}

func (e *EnrollError) Error() string {
	if e.Status == 0 {
		return e.Code
	}
	return fmt.Sprintf("%s (HTTP %d)", e.Code, e.Status)
}

// Enroll bir martalik tokenni doimiy agent tokeniga almashtiradi.
func Enroll(ctx context.Context, coreURL, caFile string, timeout time.Duration, enrollToken, version string, facts map[string]any) (*EnrollResult, error) {
	hc, err := newHTTPClient(caFile, timeout)
	if err != nil {
		return nil, err
	}
	hostname, _ := facts["hostname"].(string)
	payload, err := json.Marshal(map[string]any{
		"enroll_token":  enrollToken,
		"hostname":      hostname,
		"agent_version": version,
		"facts":         facts,
	})
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		strings.TrimRight(coreURL, "/")+"/ingest/v1/enroll", bytes.NewReader(payload))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Nazoratchi-Agent", "nazoratchi-agent/"+version)
	resp, err := hc.Do(req)
	if err != nil {
		return nil, &EnrollError{Code: "ulanib bo'lmadi: " + redact(err, enrollToken)}
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if resp.StatusCode != http.StatusOK {
		// Core xatosi {"error": {"code": ...}} ko'rinishida (TZ 9.1.1).
		var e struct {
			Error struct {
				Code string `json:"code"`
			} `json:"error"`
		}
		code := "http_error"
		if json.Unmarshal(raw, &e) == nil && e.Error.Code != "" {
			code = e.Error.Code
		}
		return nil, &EnrollError{Code: code, Status: resp.StatusCode}
	}
	var out EnrollResult
	if err := json.Unmarshal(raw, &out); err != nil || out.AgentToken == "" || out.HostID == "" {
		return nil, &EnrollError{Code: "javob noto'g'ri", Status: resp.StatusCode}
	}
	return &out, nil
}

// ---- goodbye (FR-AGT-013) ----

// Goodbye `nazoratchi-agent uninstall` paytida core'ga hostni arxivlash haqida xabar beradi
// (`POST /ingest/v1/goodbye`, Bearer token). Muvaffaqiyat faqat HTTP 200.
func Goodbye(ctx context.Context, coreURL, caFile, token, version string) error {
	hc, err := newHTTPClient(caFile, 10*time.Second)
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		strings.TrimRight(coreURL, "/")+"/ingest/v1/goodbye", strings.NewReader("{}"))
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Nazoratchi-Agent", "nazoratchi-agent/"+version)
	resp, err := hc.Do(req)
	if err != nil {
		return errors.New(redact(err, token))
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 1<<20))
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("core HTTP %d javob berdi", resp.StatusCode)
	}
	return nil
}
