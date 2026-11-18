package pb

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"mime/multipart"
	"net/http"
	"net/textproto"
	"net/url"
	"strings"
	"time"
)

// File is one upload for a file field.
type File struct {
	Name        string
	ContentType string
	Data        []byte
}

// CreateWithFiles inserts a record and uploads files into one of its file
// fields in the same request. The plain fields travel as PocketBase's
// @jsonPayload multipart part, so they keep their JSON types (arrays, numbers,
// bools) instead of being flattened to form strings.
//
// PocketBase stores the files in the order they are sent, so files[i] is
// record[fileField][i] in the returned record — callers rely on that to match
// each upload back to its stored, uniquified name.
func (c *Client) CreateWithFiles(ctx context.Context, collection string, data Record, fileField string, files []File) (Record, error) {
	body, ctype, err := multipartBody(data, fileField, files)
	if err != nil {
		return nil, err
	}
	path := "/api/collections/" + url.PathEscape(collection) + "/records"

	raw, status, err := c.sendAuthed(ctx, http.MethodPost, path, ctype, body)
	if err != nil {
		return nil, err
	}
	if status < 200 || status >= 300 {
		return nil, apiError(status, raw)
	}
	var out Record
	if err := json.Unmarshal(raw, &out); err != nil {
		return nil, err
	}
	return out, nil
}

// GetFile downloads a stored file from a record's file field. The collections
// have no public access rules, so it authenticates as the superuser like every
// other call.
func (c *Client) GetFile(ctx context.Context, collection, recordID, filename string) ([]byte, error) {
	path := "/api/files/" + url.PathEscape(collection) + "/" +
		url.PathEscape(recordID) + "/" + url.PathEscape(filename)
	raw, status, err := c.sendAuthed(ctx, http.MethodGet, path, "", nil)
	if err != nil {
		return nil, err
	}
	if status < 200 || status >= 300 {
		return nil, apiError(status, raw)
	}
	return raw, nil
}

// sendAuthed sends body as-is with the superuser token, retrying once with a
// fresh token on a 401 (as Raw does). body is a byte slice rather than a
// reader so the retry can resend it.
func (c *Client) sendAuthed(ctx context.Context, method, path, ctype string, body []byte) ([]byte, int, error) {
	raw, status, err := c.sendOnce(ctx, method, path, ctype, body)
	if err != nil || status != http.StatusUnauthorized {
		return raw, status, err
	}
	c.mu.Lock()
	c.token = ""
	c.tokenExp = time.Time{}
	c.mu.Unlock()
	return c.sendOnce(ctx, method, path, ctype, body)
}

func (c *Client) sendOnce(ctx context.Context, method, path, ctype string, body []byte) ([]byte, int, error) {
	token, err := c.authenticate(ctx)
	if err != nil {
		return nil, 0, err
	}
	var reader io.Reader
	if body != nil {
		reader = bytes.NewReader(body)
	}
	req, err := http.NewRequestWithContext(ctx, method, c.url()+path, reader)
	if err != nil {
		return nil, 0, err
	}
	if ctype != "" {
		req.Header.Set("Content-Type", ctype)
	}
	if token != "" {
		req.Header.Set("Authorization", token)
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return nil, 0, err
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, 0, err
	}
	return raw, resp.StatusCode, nil
}

func multipartBody(data Record, fileField string, files []File) ([]byte, string, error) {
	var buf bytes.Buffer
	mw := multipart.NewWriter(&buf)

	payload, err := json.Marshal(data)
	if err != nil {
		return nil, "", err
	}
	if err := mw.WriteField("@jsonPayload", string(payload)); err != nil {
		return nil, "", err
	}
	for _, f := range files {
		h := make(textproto.MIMEHeader)
		h.Set("Content-Disposition", `form-data; name="`+escapeQuotes(fileField)+
			`"; filename="`+escapeQuotes(f.Name)+`"`)
		ct := f.ContentType
		if ct == "" {
			ct = "application/octet-stream"
		}
		h.Set("Content-Type", ct)
		part, err := mw.CreatePart(h)
		if err != nil {
			return nil, "", err
		}
		if _, err := part.Write(f.Data); err != nil {
			return nil, "", err
		}
	}
	if err := mw.Close(); err != nil {
		return nil, "", err
	}
	return buf.Bytes(), mw.FormDataContentType(), nil
}

// escapeQuotes matches mime/multipart's own (unexported) escaping, so a
// filename that came from a phone cannot break out of the header.
var quoteEscaper = strings.NewReplacer("\\", "\\\\", `"`, "\\\"", "\r", "", "\n", "")

func escapeQuotes(s string) string { return quoteEscaper.Replace(s) }

// apiError builds the same *APIError do returns for a non-2xx response.
func apiError(status int, raw []byte) error {
	msg := http.StatusText(status)
	var pbErr struct {
		Message string `json:"message"`
	}
	if json.Unmarshal(raw, &pbErr) == nil && pbErr.Message != "" {
		msg = pbErr.Message
	}
	return &APIError{Status: status, Message: msg, Body: string(raw)}
}
