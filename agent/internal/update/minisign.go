// Package update — agentning imzolangan o'z-o'zini yangilashi (TZ 7.7.3, 14.5.4, FR-AGT-008).
//
// Ikki bosqich, chunki agent root emas va `/usr/local/bin` unga yopiq (`ProtectSystem=strict`):
//
//  1. Stage (agent, `nazoratchi` foydalanuvchisi): core'dan yuklaydi, imzoni tekshiradi, `StageDir` ga qo'yadi
//     va chiqadi (systemd qayta ishga tushiradi).
//  2. Apply (`ExecStartPre=+`, root, o'rnatilgan ishonchli binar): staged fayllarni **mustaqil qayta tekshiradi**
//     va faqat shundan keyin almashtiradi. Agent yozadigan hech narsaga ishonilmaydi: buzilgan agent
//     rootda ixtiyoriy binar o'rnata olmasligi shart.
package update

import (
	"bytes"
	"crypto/ed25519"
	"encoding/base64"
	"errors"
	"fmt"
	"strings"

	"golang.org/x/crypto/blake2b"
)

// PublicKey — minisign ochiq kaliti.
type PublicKey struct {
	id  [8]byte
	key ed25519.PublicKey
}

// ParsePublicKey minisign ochiq kalitini o'qiydi: faqat base64 qatori yoki `.pub` faylning to'liq matni.
func ParsePublicKey(s string) (PublicKey, error) {
	line := strings.TrimSpace(s)
	if lines := strings.Split(line, "\n"); len(lines) > 1 {
		line = strings.TrimSpace(lines[len(lines)-1]) // "untrusted comment: ..." qatori tashlanadi
	}
	raw, err := base64.StdEncoding.DecodeString(line)
	if err != nil {
		return PublicKey{}, fmt.Errorf("ochiq kalit base64 emas: %w", err)
	}
	if len(raw) != 42 || raw[0] != 'E' || raw[1] != 'd' {
		return PublicKey{}, errors.New("ochiq kalit formati noto'g'ri (42 bayt, 'Ed' kutilgan)")
	}
	var k PublicKey
	copy(k.id[:], raw[2:10])
	k.key = ed25519.PublicKey(append([]byte(nil), raw[10:]...))
	return k, nil
}

// Verify minisign imzosini (`.minisig` matni) message uchun tekshiradi. Ikkala algoritm qo'llanadi:
// "Ed" (xom xabar) va "ED" (BLAKE2b-512 xeshi; zamonaviy minisign standarti). Global imzo ham
// tekshiriladi, shuning uchun "trusted comment" ni o'zgartirib bo'lmaydi.
func (k PublicKey) Verify(message, minisig []byte) error {
	if len(minisig) > 4096 {
		return errors.New("imzo fayli juda katta")
	}
	lines := strings.Split(strings.ReplaceAll(string(minisig), "\r\n", "\n"), "\n")
	if len(lines) < 4 || !strings.HasPrefix(lines[0], "untrusted comment:") || !strings.HasPrefix(lines[2], "trusted comment: ") {
		return errors.New("imzo fayli formati noto'g'ri")
	}
	raw, err := base64.StdEncoding.DecodeString(strings.TrimSpace(lines[1]))
	if err != nil || len(raw) != 74 {
		return errors.New("imzo qatori noto'g'ri")
	}
	alg, keyID, sig := raw[0:2], raw[2:10], raw[10:]
	if !bytes.Equal(keyID, k.id[:]) {
		return errors.New("imzo boshqa kalit bilan qo'yilgan")
	}
	data := message
	switch string(alg) {
	case "Ed":
	case "ED":
		sum := blake2b.Sum512(message)
		data = sum[:]
	default:
		return fmt.Errorf("noma'lum imzo algoritmi %q", alg)
	}
	if !ed25519.Verify(k.key, data, sig) {
		return errors.New("imzo noto'g'ri")
	}
	global, err := base64.StdEncoding.DecodeString(strings.TrimSpace(lines[3]))
	if err != nil || len(global) != 64 {
		return errors.New("global imzo qatori noto'g'ri")
	}
	comment := strings.TrimPrefix(lines[2], "trusted comment: ")
	if !ed25519.Verify(k.key, append(append([]byte(nil), sig...), comment...), global) {
		return errors.New("global imzo (trusted comment) noto'g'ri")
	}
	return nil
}
