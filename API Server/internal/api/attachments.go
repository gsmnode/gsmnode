package api

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"mime"
	"net/http"
	"strings"

	"smsgateway/apiserver/internal/bootstrap"
	"smsgateway/apiserver/internal/pb"
)

// MMS attachment bytes are stored in the record's "files" field — PocketBase
// file storage, which is the pb_data volume or an S3 bucket — while the
// "attachments" JSON column keeps only the metadata. The wire contract does not
// change: clients still send and receive [{filename, content_type, data}] with
// base64 data, and the API Server converts at the edge in both directions.

// filesField is the multi-file field on messages and inbox.
const filesField = "files"

// storedAttachment is one entry of the attachments JSON column.
//
// Part indexes the record's files field. PocketBase keeps uploads in the order
// they were sent, so the index is known before the stored (uniquified) names
// are. Data is only ever set on records written before attachments moved to
// file storage; URL is a part the device reported as a link.
type storedAttachment struct {
	Filename    string `json:"filename,omitempty"`
	ContentType string `json:"content_type,omitempty"`
	Part        *int   `json:"part,omitempty"`
	Data        string `json:"data,omitempty"`
	URL         string `json:"url,omitempty"`
}

// attachmentError is a client mistake in the attachments list, reported as 400.
type attachmentError struct{ msg string }

func (e *attachmentError) Error() string { return e.msg }

// writeCreateError reports a failed createWithAttachments: a bad attachment is
// the caller's mistake, anything else is PocketBase's.
func writeCreateError(w http.ResponseWriter, err error) {
	var ae *attachmentError
	if errors.As(err, &ae) {
		writeError(w, http.StatusBadRequest, ae.msg)
		return
	}
	writeUpstreamError(w, err)
}

// splitAttachments turns request attachments into the metadata to store and
// the uploads to send. A part with data becomes an upload; a URL-only part is
// kept as metadata.
func splitAttachments(in []attachment) ([]storedAttachment, []pb.File, error) {
	stored := make([]storedAttachment, 0, len(in))
	var files []pb.File
	for i, a := range in {
		sa := storedAttachment{Filename: a.Filename, ContentType: a.ContentType, URL: a.URL}
		if strings.TrimSpace(a.Data) != "" {
			raw, err := decodeBase64(a.Data)
			if err != nil {
				return nil, nil, &attachmentError{fmt.Sprintf("attachment %d: data is not valid base64", i+1)}
			}
			if len(raw) > bootstrap.MaxAttachmentSize {
				return nil, nil, &attachmentError{fmt.Sprintf("attachment %d: larger than %d bytes", i+1, bootstrap.MaxAttachmentSize)}
			}
			part := len(files)
			sa.Part = &part
			files = append(files, pb.File{
				Name:        uploadName(a, part),
				ContentType: a.ContentType,
				Data:        raw,
			})
		}
		stored = append(stored, sa)
	}
	if len(files) > bootstrap.MaxAttachments {
		return nil, nil, &attachmentError{fmt.Sprintf("at most %d attachments with data", bootstrap.MaxAttachments)}
	}
	return stored, files, nil
}

// decodeBase64 accepts the spellings clients actually send: standard or URL
// alphabet, padded or not, with or without line breaks (Android's
// Base64.DEFAULT wraps at 76 columns).
func decodeBase64(s string) ([]byte, error) {
	s = strings.Map(func(r rune) rune {
		switch r {
		case '\n', '\r', ' ', '\t':
			return -1
		}
		return r
	}, s)
	var err error
	for _, enc := range []*base64.Encoding{
		base64.StdEncoding, base64.RawStdEncoding, base64.URLEncoding, base64.RawURLEncoding,
	} {
		var b []byte
		if b, err = enc.DecodeString(s); err == nil {
			return b, nil
		}
	}
	return nil, err
}

// uploadName is the filename sent to PocketBase. PocketBase needs one to treat
// the part as a file, and appends its own random suffix either way; the
// client's original filename — empty included — is what the metadata keeps.
func uploadName(a attachment, part int) string {
	if name := strings.TrimSpace(a.Filename); name != "" {
		return name
	}
	ext := ""
	if exts, _ := mime.ExtensionsByType(a.ContentType); len(exts) > 0 {
		ext = exts[0]
	}
	return fmt.Sprintf("attachment-%d%s", part+1, ext)
}

// createWithAttachments creates a record whose MMS attachments are uploaded
// into its files field in the same request.
func (s *Server) createWithAttachments(ctx context.Context, collection string, fields pb.Record, atts []attachment) (pb.Record, error) {
	if len(atts) == 0 {
		return s.pb.Create(ctx, collection, fields)
	}
	stored, files, err := splitAttachments(atts)
	if err != nil {
		return nil, err
	}
	fields["attachments"] = stored
	if len(files) == 0 {
		return s.pb.Create(ctx, collection, fields)
	}
	return s.pb.CreateWithFiles(ctx, collection, fields, filesField, files)
}

// loadAttachments returns a record's attachments in wire form, reading the
// bytes of each file-backed part back out of PocketBase storage. A part whose
// file cannot be read comes back without data, and the error says which —
// the caller decides whether that is fatal.
func (s *Server) loadAttachments(ctx context.Context, collection string, rec pb.Record) ([]attachment, error) {
	stored := asStoredAttachments(rec["attachments"])
	if len(stored) == 0 {
		return nil, nil
	}
	names := asStringSlice(rec[filesField])
	recID := asString(rec["id"])

	var firstErr error
	out := make([]attachment, 0, len(stored))
	for _, sa := range stored {
		a := attachment{Filename: sa.Filename, ContentType: sa.ContentType, Data: sa.Data, URL: sa.URL}
		if sa.Part != nil {
			if *sa.Part < 0 || *sa.Part >= len(names) {
				if firstErr == nil {
					firstErr = fmt.Errorf("%s/%s: attachment part %d has no stored file", collection, recID, *sa.Part)
				}
			} else if raw, err := s.pb.GetFile(ctx, collection, recID, names[*sa.Part]); err != nil {
				if firstErr == nil {
					firstErr = fmt.Errorf("%s/%s: read %s: %w", collection, recID, names[*sa.Part], err)
				}
			} else {
				a.Data = base64.StdEncoding.EncodeToString(raw)
			}
		}
		out = append(out, a)
	}
	return out, firstErr
}

// withAttachments is loadAttachments for read paths where a missing file must
// not hide the rest of the record: it logs and returns what it could read.
func (s *Server) withAttachments(ctx context.Context, collection string, rec pb.Record) []attachment {
	atts, err := s.loadAttachments(ctx, collection, rec)
	if err != nil {
		log.Printf("attachments: %v", err)
	}
	return atts
}

func (s *Server) messageOut(ctx context.Context, rec pb.Record) messageDTO {
	dto := recordToMessage(rec)
	dto.Attachments = s.withAttachments(ctx, colMessages, rec)
	return dto
}

func (s *Server) inboxOut(ctx context.Context, rec pb.Record) inboxDTO {
	dto := recordToInbox(rec)
	dto.Attachments = s.withAttachments(ctx, colInbox, rec)
	return dto
}

// asStoredAttachments coerces the stored attachments JSON into typed entries.
func asStoredAttachments(v any) []storedAttachment {
	if v == nil {
		return nil
	}
	raw, err := json.Marshal(v)
	if err != nil {
		return nil
	}
	var out []storedAttachment
	if err := json.Unmarshal(raw, &out); err != nil {
		return nil
	}
	return out
}
