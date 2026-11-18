package api

import (
	"encoding/base64"
	"errors"
	"strings"
	"testing"
)

func TestSplitAttachments(t *testing.T) {
	png := []byte("\x89PNG fake bytes")
	b64 := base64.StdEncoding.EncodeToString(png)
	// Android's Base64.DEFAULT wraps lines; the server must accept that.
	wrapped := b64[:8] + "\n" + b64[8:]

	stored, files, err := splitAttachments([]attachment{
		{Filename: "a.png", ContentType: "image/png", Data: wrapped},
		{ContentType: "image/jpeg", URL: "https://example.com/x.jpg"},
		{ContentType: "image/png", Data: base64.RawURLEncoding.EncodeToString(png)},
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(stored) != 3 || len(files) != 2 {
		t.Fatalf("got %d stored, %d files; want 3, 2", len(stored), len(files))
	}
	if stored[0].Part == nil || *stored[0].Part != 0 || stored[0].Data != "" {
		t.Errorf("first part should reference file 0 without inline data: %+v", stored[0])
	}
	if stored[1].Part != nil || stored[1].URL == "" {
		t.Errorf("URL-only part should stay metadata: %+v", stored[1])
	}
	if stored[2].Part == nil || *stored[2].Part != 1 {
		t.Errorf("third part should reference file 1: %+v", stored[2])
	}
	if string(files[0].Data) != string(png) || string(files[1].Data) != string(png) {
		t.Error("decoded bytes differ from the original")
	}
	if files[0].Name != "a.png" {
		t.Errorf("upload name = %q, want the client's filename", files[0].Name)
	}
	if !strings.HasPrefix(files[1].Name, "attachment-2") {
		t.Errorf("unnamed upload = %q, want a generated attachment-2 name", files[1].Name)
	}
}

func TestSplitAttachmentsRejectsBadBase64(t *testing.T) {
	_, _, err := splitAttachments([]attachment{{Data: "not base64 !!"}})
	var ae *attachmentError
	if !errors.As(err, &ae) {
		t.Fatalf("err = %v, want an attachmentError", err)
	}
}
