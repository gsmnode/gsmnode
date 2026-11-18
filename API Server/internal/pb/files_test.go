package pb

import (
	"bytes"
	"encoding/json"
	"io"
	"mime"
	"mime/multipart"
	"testing"
)

func TestMultipartBody(t *testing.T) {
	body, ctype, err := multipartBody(
		Record{"phone_numbers": []string{"+1"}, "encrypted": true},
		"files",
		[]File{
			{Name: `a"b.png`, ContentType: "image/png", Data: []byte("one")},
			{Name: "c.txt", Data: []byte("two")},
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	_, params, err := mime.ParseMediaType(ctype)
	if err != nil {
		t.Fatal(err)
	}
	mr := multipart.NewReader(bytes.NewReader(body), params["boundary"])

	p, err := mr.NextPart()
	if err != nil || p.FormName() != "@jsonPayload" {
		t.Fatalf("first part = %v %v, want @jsonPayload", p, err)
	}
	var payload map[string]any
	if err := json.NewDecoder(p).Decode(&payload); err != nil {
		t.Fatal(err)
	}
	if payload["encrypted"] != true {
		t.Errorf("payload lost its JSON types: %v", payload)
	}

	// Files come through in order, under the file field, with their names.
	for i, want := range []struct{ name, ctype, data string }{
		{`a"b.png`, "image/png", "one"},
		{"c.txt", "application/octet-stream", "two"},
	} {
		p, err := mr.NextPart()
		if err != nil {
			t.Fatalf("file %d: %v", i, err)
		}
		data, _ := io.ReadAll(p)
		if p.FormName() != "files" || p.FileName() != want.name ||
			p.Header.Get("Content-Type") != want.ctype || string(data) != want.data {
			t.Errorf("file %d = %q %q %q %q", i, p.FormName(), p.FileName(), p.Header.Get("Content-Type"), data)
		}
	}
}
